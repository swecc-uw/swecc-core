from bench_common.utils.github import normalize_github_url


def test_normalize_github_url_strips_git_and_slash():
    a = normalize_github_url("https://github.com/org/repo.git/")
    b = normalize_github_url("http://github.com/org/repo")
    assert a == b == "https://github.com/org/repo"


def test_normalize_github_url_adds_https_scheme():
    assert normalize_github_url("github.com/org/repo") == "https://github.com/org/repo"
