"""Bilibili attempt ordering and lazy CDN failover policy.

This module only prepares metadata and decides whether another attempt can help.
The downloader owns cancellation, workspace lifetime, network I/O and finalization.
"""

import copy
from typing import Callable

from audio_output import AudioOutputProfile
from bilibili_acceleration import (
    BILIBILI_HTTP_CHUNK_SIZE,
    STANDARD,
    TURBO,
    AccelerationPlan,
    apply_cdn_host,
    candidate_hosts,
    needs_cdn_host_switch,
    primary_host,
)


def is_aria2_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "aria2c" in message and (
        "exited" in message or "external downloader" in message
    )


def is_cdn_access_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "http error 403" in message or "http error 412" in message


def is_cdn_transport_failure(error: Exception) -> bool:
    """Return whether another Bilibili CDN may recover a broken transfer."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "http error 503",
            "winerror 10053",
            "winerror 10054",
            "connection reset",
            "connection aborted",
            "connection broken",
            "forcibly closed",
            "remote host closed",
            "remote end closed connection without response",
            "incomplete read",
            "远程主机强迫关闭",
        )
    )


class BilibiliRecovery:
    """Keep attempt metadata and admit one backup per recoverable failure.

    Attempts retain their historical tuple shape: (mode, info, plan, fallback).
    The list may grow during iteration; backups are copied only when admitted.
    """

    def __init__(
        self,
        original_info: dict,
        plan: AccelerationPlan,
        used_mode: str,
        media_type: str,
        audio_profile: AudioOutputProfile | None,
        *,
        deepcopy_fn: Callable = copy.deepcopy,
        primary_host_fn: Callable = primary_host,
        needs_cdn_host_switch_fn: Callable = needs_cdn_host_switch,
        apply_cdn_host_fn: Callable = apply_cdn_host,
        candidate_hosts_fn: Callable = candidate_hosts,
        acceleration_plan_cls: Callable = AccelerationPlan,
    ) -> None:
        self.original_info = original_info
        self.used_mode = used_mode
        self.media_type = media_type
        self._deepcopy = deepcopy_fn
        self._apply_cdn_host = apply_cdn_host_fn
        self._acceleration_plan = acceleration_plan_cls
        original_cdn_host = primary_host_fn(original_info)
        cdn_switched = needs_cdn_host_switch_fn(original_info, plan.cdn_host)
        if cdn_switched:
            optimized_info = deepcopy_fn(original_info)
            apply_cdn_host_fn(optimized_info, plan.cdn_host)
        else:
            optimized_info = original_info

        prepared_infos = [original_info]
        if optimized_info is not original_info:
            prepared_infos.append(optimized_info)
        for prepared in prepared_infos:
            prepared["_media_type"] = media_type
            if audio_profile:
                prepared["_audio_format_used"] = audio_profile.used
                prepared["_audio_output_ext"] = audio_profile.output_ext

        self.attempts = [(used_mode, optimized_info, plan, False)]
        if used_mode == TURBO:
            self.attempts.append((STANDARD, deepcopy_fn(optimized_info), plan, True))

        original_plan = acceleration_plan_cls(False, original_cdn_host, BILIBILI_HTTP_CHUNK_SIZE)
        if cdn_switched:
            self.attempts.append((STANDARD, original_info, original_plan, used_mode == TURBO))

        represented_hosts = {
            attempt_plan.cdn_host
            for _, _, attempt_plan, _ in self.attempts
            if attempt_plan.cdn_host
        }
        # A short successful probe cannot guarantee a complete long transfer.
        self.backup_hosts = [
            host for host in candidate_hosts_fn(original_info)
            if host not in represented_hosts
        ]

    def retry_after(
        self,
        attempt_index: int,
        error: Exception,
        audio_profile: AudioOutputProfile | None,
        *,
        is_aria2_failure_fn: Callable = is_aria2_failure,
        is_cdn_access_failure_fn: Callable = is_cdn_access_failure,
        is_cdn_transport_failure_fn: Callable = is_cdn_transport_failure,
    ) -> bool:
        """Admit a backup if appropriate, then evaluate the next attempt."""
        attempt_mode, _, attempt_plan, _ = self.attempts[attempt_index]
        if is_cdn_access_failure_fn(error) or is_cdn_transport_failure_fn(error):
            while self.backup_hosts:
                backup_host = self.backup_hosts.pop(0)
                backup_info = self._deepcopy(self.original_info)
                if not self._apply_cdn_host(backup_info, backup_host):
                    continue
                backup_info["_media_type"] = self.media_type
                if audio_profile:
                    backup_info["_audio_format_used"] = audio_profile.used
                    backup_info["_audio_output_ext"] = audio_profile.output_ext
                self.attempts.append((
                    STANDARD,
                    backup_info,
                    self._acceleration_plan(True, backup_host, BILIBILI_HTTP_CHUNK_SIZE),
                    self.used_mode == TURBO,
                ))
                break

        next_is_standard = (
            attempt_index + 1 < len(self.attempts)
            and self.attempts[attempt_index + 1][0] == STANDARD
        )
        can_retry_aria2 = (
            attempt_mode == TURBO
            and is_aria2_failure_fn(error)
            and next_is_standard
        )
        can_retry_cdn = (
            is_cdn_access_failure_fn(error)
            and any(
                future_plan.cdn_host != attempt_plan.cdn_host
                for _, _, future_plan, _ in self.attempts[attempt_index + 1:]
            )
        )
        can_retry_transport = (
            is_cdn_transport_failure_fn(error)
            and any(
                future_plan.cdn_host != attempt_plan.cdn_host
                for _, _, future_plan, _ in self.attempts[attempt_index + 1:]
            )
        )
        return bool(can_retry_aria2 or can_retry_cdn or can_retry_transport)
