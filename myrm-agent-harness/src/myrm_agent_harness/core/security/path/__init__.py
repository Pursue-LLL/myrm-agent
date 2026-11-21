"""Path security domain — the single import surface for every path protection rule.

Seven modules, one responsibility each:

- ``pattern``    — glob matcher engine (`*`/`?`/`**`/character classes, case-insensitive by default)
- ``filesystem`` — generic path safety: dangerous roots, device names, home spelling, boundary, safe join, coercion
- ``typed_path`` — the file a typed path opens: home spelling, workspace join, links followed
- ``respelling`` — the on-disk name of a path typed with quotes, compatibility characters or decomposed accents
- ``rules``      — protected-path policy: which files must not be touched, and the predicates that read the rules
- ``bounded_read`` — text reads of untrusted files that cannot exhaust memory or block on a FIFO or device
- ``confined_write`` — new files below a trusted directory that a symlink or hard link cannot redirect

Consumers import predicates from this package (``core.security.path``) and reach for
``core.security.path.pattern`` only when they need the raw matcher. ``__all__`` is
declared so the ``agent.security.path_security`` shim forwards exactly this API — without
it, a wildcard re-export would also republish ``os``/``Path`` and invite callers to
bypass the predicates that carry the security policy.

[INPUT]
- path.bounded_read (POS: Bounded text read of files in an untrusted folder)
- path.confined_write (POS: Exclusive file creation below a trusted directory, decided on descriptors so no link redirects it)
- path.filesystem (POS: Generic filesystem path safety — no product protection policy)
- path.respelling (POS: Finds the file a model meant when its typed spelling differs from the disk)
- path.rules (POS: Protected-path policy)
- path.typed_path (POS: The one definition of which file a tool opens for the text it was given)

[OUTPUT]
- is_dangerous_path, covers_dangerous_path, is_blocked_device_path, is_network_or_nt_path, network_path_refusal, expand_home, is_within_boundary, safe_join_path, coerce_filesystem_path, is_content_not_path
- opened_path, find_existing_unicode_path
- read_text_bounded, BoundedRead, ReadRefusal
- open_directory_beneath, ConfinedDirectory, UnsafeDirectoryError
- is_sensitive_file, is_protected_instruction_file, is_evidence_readonly_file, is_executable_git_metadata_file
- DANGEROUS_PATHS, BLOCKED_DEVICE_NAMES, MAX_PATH_LENGTH
- SENSITIVE_FILE_PATTERNS, PROTECTED_INSTRUCTION_PATTERNS, EVIDENCE_READONLY_PATTERNS
- EXECUTABLE_GIT_METADATA, EXECUTABLE_GIT_METADATA_PATTERNS

[POS]
Aggregation facade for the path security domain.
"""

from myrm_agent_harness.core.security.path.bounded_read import (
    BoundedRead as BoundedRead,
)
from myrm_agent_harness.core.security.path.bounded_read import (
    ReadRefusal as ReadRefusal,
)
from myrm_agent_harness.core.security.path.bounded_read import (
    read_text_bounded as read_text_bounded,
)
from myrm_agent_harness.core.security.path.confined_write import (
    ConfinedDirectory as ConfinedDirectory,
)
from myrm_agent_harness.core.security.path.confined_write import (
    UnsafeDirectoryError as UnsafeDirectoryError,
)
from myrm_agent_harness.core.security.path.confined_write import (
    open_directory_beneath as open_directory_beneath,
)
from myrm_agent_harness.core.security.path.filesystem import (
    BLOCKED_DEVICE_NAMES as BLOCKED_DEVICE_NAMES,
)
from myrm_agent_harness.core.security.path.filesystem import (
    DANGEROUS_PATHS as DANGEROUS_PATHS,
)
from myrm_agent_harness.core.security.path.filesystem import (
    MAX_PATH_LENGTH as MAX_PATH_LENGTH,
)
from myrm_agent_harness.core.security.path.filesystem import (
    coerce_filesystem_path as coerce_filesystem_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    covers_dangerous_path as covers_dangerous_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    expand_home as expand_home,
)
from myrm_agent_harness.core.security.path.filesystem import (
    is_blocked_device_path as is_blocked_device_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    is_content_not_path as is_content_not_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    is_dangerous_path as is_dangerous_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    is_network_or_nt_path as is_network_or_nt_path,
)
from myrm_agent_harness.core.security.path.filesystem import (
    is_within_boundary as is_within_boundary,
)
from myrm_agent_harness.core.security.path.filesystem import (
    network_path_refusal as network_path_refusal,
)
from myrm_agent_harness.core.security.path.filesystem import (
    safe_join_path as safe_join_path,
)
from myrm_agent_harness.core.security.path.respelling import (
    find_existing_unicode_path as find_existing_unicode_path,
)
from myrm_agent_harness.core.security.path.rules import (
    EVIDENCE_READONLY_PATTERNS as EVIDENCE_READONLY_PATTERNS,
)
from myrm_agent_harness.core.security.path.rules import (
    EXECUTABLE_GIT_METADATA as EXECUTABLE_GIT_METADATA,
)
from myrm_agent_harness.core.security.path.rules import (
    EXECUTABLE_GIT_METADATA_PATTERNS as EXECUTABLE_GIT_METADATA_PATTERNS,
)
from myrm_agent_harness.core.security.path.rules import (
    PROTECTED_INSTRUCTION_PATTERNS as PROTECTED_INSTRUCTION_PATTERNS,
)
from myrm_agent_harness.core.security.path.rules import (
    SENSITIVE_FILE_PATTERNS as SENSITIVE_FILE_PATTERNS,
)
from myrm_agent_harness.core.security.path.rules import (
    is_evidence_readonly_file as is_evidence_readonly_file,
)
from myrm_agent_harness.core.security.path.rules import (
    is_executable_git_metadata_file as is_executable_git_metadata_file,
)
from myrm_agent_harness.core.security.path.rules import (
    is_protected_instruction_file as is_protected_instruction_file,
)
from myrm_agent_harness.core.security.path.rules import (
    is_sensitive_file as is_sensitive_file,
)
from myrm_agent_harness.core.security.path.typed_path import (
    opened_path as opened_path,
)

__all__ = (
    "BLOCKED_DEVICE_NAMES",
    "DANGEROUS_PATHS",
    "EVIDENCE_READONLY_PATTERNS",
    "EXECUTABLE_GIT_METADATA",
    "EXECUTABLE_GIT_METADATA_PATTERNS",
    "MAX_PATH_LENGTH",
    "PROTECTED_INSTRUCTION_PATTERNS",
    "SENSITIVE_FILE_PATTERNS",
    "BoundedRead",
    "ConfinedDirectory",
    "ReadRefusal",
    "UnsafeDirectoryError",
    "coerce_filesystem_path",
    "covers_dangerous_path",
    "expand_home",
    "find_existing_unicode_path",
    "is_blocked_device_path",
    "is_content_not_path",
    "is_dangerous_path",
    "is_evidence_readonly_file",
    "is_executable_git_metadata_file",
    "is_network_or_nt_path",
    "is_protected_instruction_file",
    "is_sensitive_file",
    "is_within_boundary",
    "network_path_refusal",
    "open_directory_beneath",
    "opened_path",
    "read_text_bounded",
    "safe_join_path",
)
