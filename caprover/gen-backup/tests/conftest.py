import json

import pytest
from gen_backup.cli import bundled_template


@pytest.fixture()
def template_config():
    """The real template's config-captain.json, for before/after assertions."""
    template_dir = bundled_template()
    with open(template_dir / "data" / "config-captain.json") as f:
        return json.load(f)


@pytest.fixture()
def template_meta():
    """The real template's backup.json, for before/after assertions."""
    template_dir = bundled_template()
    with open(template_dir / "meta" / "backup.json") as f:
        return json.load(f)
