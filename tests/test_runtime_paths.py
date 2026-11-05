from pathlib import Path

from library import initial_location
from runtime_paths import configuration_root, instance_id


def test_packaged_storage_survives_installation_directory_change(tmp_path):
    env = {'LOCALAPPDATA': str(tmp_path / 'profile')}
    first = configuration_root(tmp_path / 'install-v1', frozen=True, environ=env)
    second = configuration_root(tmp_path / 'install-v2', frozen=True, environ=env)
    assert first == second == tmp_path / 'profile' / 'Ai4PDF'
    assert initial_location(first, environ=env) == (first / 'data', False)
    assert instance_id(first) == instance_id(second)


def test_source_layout_and_explicit_overrides_remain_compatible(tmp_path):
    assert configuration_root(tmp_path, frozen=False, environ={}) == tmp_path
    home = configuration_root(tmp_path, frozen=True, environ={'AI4PDF_HOME': str(tmp_path / 'isolated')})
    assert home == tmp_path / 'isolated'
    assert initial_location(home, environ={'AI4PDF_DATA': str(tmp_path / 'external')}) == (tmp_path / 'external', True)


def test_migrated_library_is_loaded_from_user_profile(tmp_path):
    import json
    actual = tmp_path / 'external'
    actual.mkdir()
    profile = tmp_path / 'profile'
    profile.mkdir()
    (profile / 'library-location.json').write_text(json.dumps({'path': str(actual)}))
    assert initial_location(profile, environ={}) == (actual, False)
