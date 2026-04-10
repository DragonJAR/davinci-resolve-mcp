"""Live API validation tests — require DaVinci Resolve running."""

import sys

import pytest

RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
sys.path.insert(0, RESOLVE_MODULES)


def _resolve_available():
    """Check if DaVinci Resolve is running and accessible."""
    try:
        import DaVinciResolveScript as dvr

        resolve = dvr.scriptapp("Resolve")
        return resolve is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _resolve_available(), reason="DaVinci Resolve not running")


@pytest.fixture(scope="module")
def resolve():
    import DaVinciResolveScript as dvr

    r = dvr.scriptapp("Resolve")
    if not r:
        pytest.skip("DaVinci Resolve not running")
    return r


@pytest.fixture(scope="module")
def project(resolve):
    pm = resolve.GetProjectManager()
    p = pm.GetCurrentProject()
    if not p:
        pytest.skip("No project open in Resolve")
    return p


class TestResolveBasic:
    def test_version_string(self, resolve):
        version = resolve.GetVersionString()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_product_name(self, resolve):
        name = resolve.GetProductName()
        assert isinstance(name, str)

    def test_current_page(self, resolve):
        page = resolve.GetCurrentPage()
        assert page in ("edit", "cut", "color", "fusion", "fairlight", "deliver")


class TestProjectManager:
    def test_get_current_project(self, project):
        assert project is not None

    def test_project_name(self, project):
        name = project.GetName()
        assert isinstance(name, str)


class TestMediaPool:
    def test_get_media_pool(self, project):
        mp = project.GetMediaPool()
        assert mp is not None

    def test_root_folder(self, project):
        mp = project.GetMediaPool()
        root = mp.GetRootFolder()
        assert root is not None
        assert root.GetName()


class TestTimeline:
    def test_current_timeline(self, project):
        timeline = project.GetCurrentTimeline()
        if timeline:
            assert isinstance(timeline.GetName(), str)
            assert timeline.GetTrackCount("video") >= 0
