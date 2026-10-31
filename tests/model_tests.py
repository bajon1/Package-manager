import pytest
from src.model import (Version, Constraint, Requirement, PackageVersion, Repository,
                          State, parse_alternative, alternative_to_str, normalize_name)

V = Version.parse


def test_version_compare():
    assert V("1.10") > V("1.9")
    assert V("1.0") == V("1.0.0")
    assert V("1.0") <= V("1.0.0")
    assert len({V("1.0"), V("1.0.0")}) == 1
    assert V("0").version == (0,)


@pytest.mark.parametrize("bad", ["", "1..0", "1.0-beta", "-1", "+1", "1_0", "1."])
def test_version_errors(bad):
    with pytest.raises(ValueError):
        V(bad)


def test_normalize_name():
    assert normalize_name("Foo_Bar") == normalize_name("foo-bar") == normalize_name("foo.bar") == "foo-bar"


def test_constraint():
    assert Constraint(">=", V("2.0")).matches(V("2.5"))
    assert not Constraint(">=", V("2.0")).matches(V("1.9"))
    assert Constraint("!=", V("1.0")).matches(V("1.1"))
    assert Constraint("==", V("1.0")).matches(V("1.0.0"))
    assert str(Constraint(">=", V("2.0"))) == ">=2.0"


def test_requirement_matches():
    r = Requirement.parse("lib >=1.0 <2.0")
    assert r.matches(V("1.0")) and r.matches(V("1.5"))
    assert not r.matches(V("2.0")) and not r.matches(V("0.9"))
    assert Requirement.parse("lib").matches(V("3.7"))          # brak ograniczeń


@pytest.mark.parametrize("text", ["lib>=1.0,<2.0", "lib >= 1.0 < 2.0", "LIB >=1.0   <2.0", "lib>=1.0 , <2.0"])
def test_requirement_syntax_variants(text):
    assert Requirement.parse(text) == Requirement.parse("lib >=1.0 <2.0")


def test_requirement_name_normalized():
    assert Requirement.parse("Lib_X").package == "lib-x"
    assert Requirement.parse("lib==2.0") == Requirement.parse("lib == 2.0")


@pytest.mark.parametrize("bad", ["", "lib 2.0", "lib =>2", "lib >=", "lib>=1..0", "lib >=1.0 |", "json-fast | json-slow", "lib,>=1.0", ">=1.0"])
def test_requirement_errors(bad):
    with pytest.raises(ValueError):
        Requirement.parse(bad)


def test_requirement_str():
    assert str(Requirement.parse("lib>=1.0,<2.0")) == "lib >=1.0 <2.0"


def test_alternative():
    alt = parse_alternative("json-fast | json-slow >=1.0")
    assert [r.package for r in alt] == ["json-fast", "json-slow"]
    assert alternative_to_str(alt) == "json-fast | json-slow >=1.0"
    with pytest.raises(ValueError):
        parse_alternative("a |")


def make_repo():
    def pv(p, v, requires=(), conflicts=()):
        return PackageVersion(p, V(v), tuple(parse_alternative(t) for t in requires),
                              tuple(Requirement.parse(c) for c in conflicts))
    return Repository([
        pv("lib", "1.0"), pv("lib", "2.0"), pv("lib", "1.5"),
        pv("app", "1.0", requires=["lib", "ghost"]),
    ])


def test_repository_order_and_obsolescence():
    repo = make_repo()
    assert [str(v.version) for v in repo.versions("lib")] == ["2.0", "1.5", "1.0"]
    assert repo.obsolescence("lib", V("2.0")) == 0
    assert repo.obsolescence("lib", V("1.0")) == 2
    assert repo.versions("nie-ma") == []
    assert sorted(repo.package_names()) == ["app", "lib"]


def test_repository_matching():
    repo = make_repo()
    got = repo.matching(Requirement.parse("lib <2.0"))
    assert [str(p) for p in got] == ["lib==1.5", "lib==1.0"]
    assert repo.matching(Requirement.parse("ghost")) == []


def test_repository_warnings():
    w = make_repo().warnings()
    assert len(w) == 1 and "ghost" in w[0] and "app==1.0" in w[0]


def test_state():
    s = State()
    s.install("app", V("2.0"), manual=True)
    s.install("lib", V("2.0"))
    assert s.version_of("app") == V("2.0")
    assert s.version_of("zzz") is None
    assert s.manual == {"app"}
    assert "app 2.0" in str(s) and "lib 2.0" in str(s)


def test_package_version_str():
    assert str(PackageVersion("app", V("2.0"))) == "app==2.0"