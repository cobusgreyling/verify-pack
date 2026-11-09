"""Claim and command patterns. The four completion claims from claim-ledger."""

from __future__ import annotations

import re

FENCE = re.compile(r"```.*?```", re.DOTALL)
EXIT_HEADER = re.compile(r"\s*exit:\s*(-?\d+)\b", re.IGNORECASE)
EXIT_CODE = re.compile(r"\bexit code:\s*(-?\d+)\b", re.IGNORECASE)
PASSED_COUNT = re.compile(r"\b(\d+)\s+passed\b", re.IGNORECASE)
FAILED_COUNT = re.compile(r"\b(\d+)\s+failed\b", re.IGNORECASE)

TEST_COMMAND = re.compile(
    r"(?:^|[;&|\n]\s*)(?:pytest|py\.test|npm test|npm run test|pnpm test|pnpm run test|"
    r"yarn test|bun test|go test|cargo test)\b|"
    r"\b(?:python(?:3)?\s+-m\s+(?:pytest|unittest)|uv run pytest)\b",
    re.IGNORECASE,
)
BUILD_COMMAND = re.compile(
    r"(?:^|[;&|\n]\s*)(?:npm run build|pnpm(?: run)? build|yarn build|bun run build|"
    r"cargo build|go build|tsc|mypy|pyright)\b",
    re.IGNORECASE,
)
COMMIT_COMMAND = re.compile(r"\bgit commit\b", re.IGNORECASE)
PUSH_COMMAND = re.compile(r"\bgit push\b", re.IGNORECASE)

COUNT_CLAIM = re.compile(r"\b(?:all\s+)?(\d+)\s+tests?\s+passed\b", re.IGNORECASE)
TESTS_CLAIM = re.compile(
    r"(?<!\d\s)\btests passed\b|\ball tests pass(?:ed)?\b|"
    r"\btest suite is green\b|\btests are (?:green|passing)\b",
    re.IGNORECASE,
)
BUILD_CLAIM = re.compile(
    r"\bbuild (?:succeeded|passed|is green)\b|\btypecheck passed\b|"
    r"\btype check passed\b|\bno type errors\b",
    re.IGNORECASE,
)
COMMITTED_CLAIM = re.compile(r"\bcommitted\b", re.IGNORECASE)
PUSHED_CLAIM = re.compile(r"\bpushed\b", re.IGNORECASE)

# Info detectors. RegexDetector compiles these case-insensitively.
TESTS_SIGNAL = (
    r"(?<!\d\s)\btests passed\b|\ball tests pass(?:ed)?\b|"
    r"\btest suite is green\b|\btests are (?:green|passing)\b|"
    r"\b(?:all\s+)?\d+\s+tests?\s+passed\b"
)
BUILD_SIGNAL = (
    r"\bbuild (?:succeeded|passed|is green)\b|\btypecheck passed\b|"
    r"\btype check passed\b|\bno type errors\b"
)
TEST_COMMAND_SIGNAL = (
    r"(?:^|[;&|\n]\s*)(?:pytest|py\.test|npm test|npm run test|pnpm test|pnpm run test|"
    r"yarn test|bun test|go test|cargo test)\b|"
    r"\b(?:python(?:3)?\s+-m\s+(?:pytest|unittest)|uv run pytest)\b"
)
BUILD_COMMAND_SIGNAL = (
    r"(?:^|[;&|\n]\s*)(?:npm run build|pnpm(?: run)? build|yarn build|bun run build|"
    r"cargo build|go build|tsc|mypy|pyright)\b"
)
