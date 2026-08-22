import pytest
from app.parser import parse


def test_plain_text():
    r = parse("buy CO2 sensor")
    assert r.priority == "normal"
    assert r.est_min == 30
    assert r.domain is None
    assert r.raw_text == "buy CO2 sensor"


def test_urgent_prefix():
    r = parse("!! deploy hotfix")
    assert r.priority == "urgent"
    assert r.raw_text == "deploy hotfix"


def test_high_prefix():
    r = parse("! pick up dog food")
    assert r.priority == "high"
    assert r.raw_text == "pick up dog food"


def test_time_prefix():
    r = parse("5: check pH")
    assert r.est_min == 5
    assert r.raw_text == "check pH"


def test_domain_prefix_short():
    r = parse("h: calibrate pH probe")
    assert r.domain == "hydroponics"
    assert r.raw_text == "calibrate pH probe"


def test_domain_prefix_long():
    r = parse("hydroponics: top off reservoir")
    assert r.domain == "hydroponics"


def test_combined_all_prefixes():
    r = parse("!! 10: w: fix staging env vars")
    assert r.priority == "urgent"
    assert r.est_min == 10
    assert r.domain == "work"
    assert r.raw_text == "fix staging env vars"


def test_time_before_domain():
    r = parse("5: h: check pH")
    assert r.est_min == 5
    assert r.domain == "hydroponics"
    assert r.raw_text == "check pH"


def test_min_est_min_clamped():
    r = parse("0: quick task")
    assert r.est_min == 1


def test_whitespace_trimmed():
    r = parse("  !!  5:  w:  deploy   ")
    assert r.priority == "urgent"
    assert r.est_min == 5
    assert r.domain == "work"
    assert r.raw_text == "deploy"
