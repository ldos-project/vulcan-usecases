"""Substitute `{{ANVIL_DSL}}` in a config YAML with libvulcan's policy prompt.

Returns the path to a temp YAML; callers own its lifetime.
"""
import os
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_DSL_PATH = os.path.join(
    _HERE, "libcachesim", "libvulcan", "prompts", "vulcan_policy_prompt.md"
)


def read_dsl() -> str:
    with open(_DSL_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def indent(text: str, prefix: str) -> str:
    return "\n".join((prefix + line) if line else "" for line in text.splitlines())


def create_config(src_yaml: str) -> str:
    """Read src_yaml, substitute {{ANVIL_DSL}} with the DSL, write a temp YAML.

    Substitution is indentation-aware: the placeholder is replaced with the DSL
    text indented to match whatever prefix appears before `{{ANVIL_DSL}}` on
    its line. This lets the placeholder sit inside a YAML block scalar without
    corrupting the block's indentation.
    """
    with open(src_yaml, "r", encoding="utf-8") as fh:
        text = fh.read()
    dsl = read_dsl()
    lines_out = []
    for line in text.splitlines():
        if "{{ANVIL_DSL}}" in line:
            prefix = line[: line.index("{{ANVIL_DSL}}")]
            lines_out.append(indent(dsl, prefix))
        else:
            lines_out.append(line)
    out_text = "\n".join(lines_out) + ("\n" if text.endswith("\n") else "")
    fd, path = tempfile.mkstemp(prefix="config_anvil_", suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out_text)
    return path
