"""The publish preflight for the poster bundle.

`scripts/check_poster.py` is the last thing between the working tree and a
stranger's browser: the bundle is dragged onto a static host by hand, so no
deploy step and no server ever reads it again. Every rule it enforces already
existed in prose in `MARKETING_CLOSED_ALPHA.md` or `LAUNCH_OPERATIONS.md` and
was, until it, kept by remembering to.

Two things are tested here. The tree itself must pass at the build stage, so
an edit that quietly breaks the poster fails the suite rather than the launch.
And each check must actually fire: a bundle with a leak, a drifted board, an
edited locked sentence, or a stale cache token has to come back a blocker, not
an `ok`.
"""

from __future__ import annotations

import json
import random
import shutil

import pytest

from scripts import check_poster


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bundle(tmp_path):
    """A writable copy of the real bundle, to be broken one way per test."""
    target = tmp_path / "public"
    shutil.copytree(check_poster.BUNDLE, target)
    return target


@pytest.fixture
def manifest(tmp_path, bundle):
    """A cache-token manifest recorded against that copy."""
    path = tmp_path / "poster.json"
    assert check_poster.accept_token(bundle, path, force=False) == 0
    return path


def run(bundle, manifest, stage="build"):
    return check_poster.run_checks(bundle, stage, manifest)


def blockers(findings, check=None):
    return [
        f.message
        for f in findings
        if f.level == check_poster.BLOCKER and (check is None or f.check == check)
    ]


def token(bundle):
    """The bundle's current cache token, so these tests never pin a literal."""
    tokens, _ = check_poster.token_scan(bundle)
    assert len(tokens) == 1, f"the tree should carry one token, found {sorted(tokens)}"
    return tokens.pop()


def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture is stale: {old!r} is not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# the tree as it stands
# ---------------------------------------------------------------------------


def test_repository_bundle_passes_build_stage():
    findings = check_poster.run_checks(check_poster.BUNDLE, "build", check_poster.MANIFEST)
    assert blockers(findings) == []


def test_publish_stage_blocks_on_the_two_placeholders():
    findings = check_poster.run_checks(check_poster.BUNDLE, "publish", check_poster.MANIFEST)
    messages = blockers(findings, "gate")
    assert any("data-endpoint" in m for m in messages)
    assert any("data-contact" in m for m in messages)


def test_filled_placeholders_clear_the_publish_stage(bundle, manifest):
    index = bundle / "index.html"
    edit(index, 'data-endpoint=""', 'data-endpoint="https://tally.so/r/abc123"')
    edit(index, 'data-contact=""', 'data-contact="operator@spoilsofempire.com"')
    assert blockers(run(bundle, manifest, "publish")) == []


def test_the_placeholder_is_read_off_the_form_not_the_comment_naming_it(bundle, manifest):
    """index.html documents both placeholders in a comment that names the tags.

    Matching the first `<form id="apply-form">` in the file finds the prose,
    which has no attributes at all, and reports the gate as absent rather than
    unfilled.
    """
    edit(bundle / "index.html", 'data-endpoint=""', 'data-endpoint="https://tally.so/r/abc123"')
    html = (bundle / "index.html").read_text(encoding="utf-8")
    assert check_poster.attribute(html, "form", "apply-form", "data-endpoint") == (
        "https://tally.so/r/abc123"
    )


def test_an_http_endpoint_is_refused_at_every_stage(bundle, manifest):
    edit(bundle / "index.html", 'data-endpoint=""', 'data-endpoint="http://tally.so/r/abc123"')
    assert any("not https" in m for m in blockers(run(bundle, manifest), "gate"))


def test_a_personal_inbox_as_operator_contact_is_a_note_not_a_blocker(bundle, manifest):
    edit(bundle / "index.html", 'data-contact=""', 'data-contact="someone@gmail.com"')
    findings = run(bundle, manifest)
    assert blockers(findings, "gate") == []
    assert any("personal inbox" in f.message for f in findings)


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------


def test_a_sea_texture_is_refused(bundle, manifest):
    (bundle / "textures" / "sea.jpg").write_bytes(b"\xff\xd8\xff")
    assert any("no sea" in m for m in blockers(run(bundle, manifest), "inventory"))


def test_a_missing_required_file_is_refused(bundle, manifest):
    (bundle / "board3d.js").unlink()
    assert any("board3d.js" in m for m in blockers(run(bundle, manifest), "inventory"))


def test_a_missing_terrain_texture_is_refused(bundle, manifest):
    """The board names three terrains. A texture for one of them is not optional."""
    (bundle / "textures" / "hills.jpg").unlink()
    assert any("hills" in m for m in blockers(run(bundle, manifest), "inventory"))


def test_a_stray_file_is_a_note_because_it_would_be_published(bundle, manifest):
    (bundle / "notes-to-self.txt").write_text("draft copy", encoding="utf-8")
    findings = run(bundle, manifest)
    assert blockers(findings, "inventory") == []
    assert any("notes-to-self.txt" in f.message for f in findings)


# ---------------------------------------------------------------------------
# locked copy
# ---------------------------------------------------------------------------


def test_an_edited_locked_sentence_is_refused(bundle, manifest):
    # The visible sentence, not the og:description that paraphrases it: the
    # copy check reads rendered text, and meta content is not rendered.
    edit(
        bundle / "index.html",
        "an agent try to rule a world you cannot touch.\n  </p>",
        "an agent try to rule a world you built.\n  </p>",
    )
    assert any("locked sentence" in m for m in blockers(run(bundle, manifest), "copy"))


def test_an_edited_proof_line_is_refused(bundle, manifest):
    edit(bundle / "index.html", "7,200 model turns", "10,000 model turns")
    assert any("proof line" in m for m in blockers(run(bundle, manifest), "copy"))


def test_a_dropped_offer_bullet_is_refused(bundle, manifest):
    edit(bundle / "index.html", "<li>Invite only. Cap 30.</li>", "")
    assert any("offer bullet 1" in m for m in blockers(run(bundle, manifest), "copy"))


def test_a_dropped_reply_promise_is_refused(bundle, manifest):
    edit(bundle / "index.html", "You will hear back within 7 days, either way.", "")
    assert any("reply promise" in m for m in blockers(run(bundle, manifest), "copy"))


def test_a_gutted_privacy_notice_is_refused(bundle, manifest):
    edit(bundle / "index.html", "To delete, write to", "")
    assert any("privacy notice" in m for m in blockers(run(bundle, manifest), "copy"))


def test_off_card_wording_is_refused(bundle, manifest):
    edit(bundle / "index.html", "<h2 id=\"offer-heading\"", "<h2>Leaderboard</h2><h2 id=\"offer-heading\"")
    assert any("leaderboard" in m for m in blockers(run(bundle, manifest), "copy"))


def test_the_offer_bullet_saying_no_prize_is_not_mistaken_for_a_prize(bundle, manifest):
    """`prize` and `ranking` appear on the page inside the promise not to have

    either. A word list that flagged them would fail the page for keeping the
    card, which is why neither is on it.
    """
    assert blockers(run(bundle, manifest), "copy") == []


# ---------------------------------------------------------------------------
# replay and board
# ---------------------------------------------------------------------------


def test_a_leaking_replay_is_refused(bundle, manifest):
    replay = json.loads((bundle / "replay.json").read_text(encoding="utf-8"))
    replay["frames"][0]["pieces"][0]["gold"] = 250
    (bundle / "replay.json").write_text(json.dumps(replay), encoding="utf-8")
    assert any("leakage test" in m for m in blockers(run(bundle, manifest), "replay"))


def test_a_replay_naming_a_city_the_board_cannot_draw_is_refused(bundle, manifest):
    replay = json.loads((bundle / "replay.json").read_text(encoding="utf-8"))
    replay["frames"][0]["pieces"][0]["city_id"] = "atlantis"
    (bundle / "replay.json").write_text(json.dumps(replay), encoding="utf-8")
    assert any("atlantis" in m for m in blockers(run(bundle, manifest), "replay"))


def test_a_replay_on_a_different_map_is_refused(bundle, manifest):
    replay = json.loads((bundle / "replay.json").read_text(encoding="utf-8"))
    replay["map"] = "calib_12_s3.json"
    (bundle / "replay.json").write_text(json.dumps(replay), encoding="utf-8")
    assert any("draws" in m for m in blockers(run(bundle, manifest), "replay"))


def test_a_board_drifted_from_the_map_is_refused(bundle, manifest):
    edit(bundle / "board.js", '"x": 0.4665', '"x": 0.5000')
    assert any("drifted" in m for m in blockers(run(bundle, manifest), "board"))


# ---------------------------------------------------------------------------
# cache token
# ---------------------------------------------------------------------------


def test_two_tokens_in_one_bundle_are_refused(bundle, manifest):
    """The bug this check was written for.

    index.html carried `?v=h2` while atlas.js imported `board3d.js?v=h1`. A
    bump made by the documented convention -- by hand, on the file you edited
    -- moves one and leaves the other, and a returning visitor gets a new
    atlas.js against a cached board3d.js.
    """
    now = token(bundle)
    edit(bundle / "atlas.js", f"board3d.js?v={now}", f"board3d.js?v={now}-stale")
    assert any("more than one cache token" in m for m in blockers(run(bundle, manifest), "token"))


def test_changed_assets_under_an_unchanged_token_are_refused(bundle, manifest):
    edit(bundle / "atlas.css", "body", "body /* touched */")
    assert any("did not" in m for m in blockers(run(bundle, manifest), "token"))


def test_bumping_the_token_everywhere_clears_it(bundle, manifest):
    edit(bundle / "atlas.css", "body", "body /* touched */")
    now = token(bundle)
    for name in ("index.html", "atlas.js", "board3d.js"):
        path = bundle / name
        path.write_text(
            path.read_text(encoding="utf-8").replace(f"?v={now}", f"?v={now}next"), encoding="utf-8"
        )
    assert check_poster.accept_token(bundle, manifest, force=False) == 0
    assert blockers(run(bundle, manifest), "token") == []


def test_accept_token_refuses_to_record_changed_assets_under_the_same_token(bundle, manifest):
    edit(bundle / "atlas.css", "body", "body /* touched */")
    assert check_poster.accept_token(bundle, manifest, force=False) == 1
    assert check_poster.accept_token(bundle, manifest, force=True) == 0


def test_an_asset_that_loses_its_token_is_refused(bundle, manifest):
    edit(bundle / "index.html", f'href="atlas.css?v={token(bundle)}"', 'href="atlas.css"')
    assert any("set of assets" in m for m in blockers(run(bundle, manifest), "token"))


def test_a_missing_manifest_is_refused(bundle, tmp_path):
    findings = run(bundle, tmp_path / "absent.json")
    assert any("does not exist" in m for m in blockers(findings, "token"))


# ---------------------------------------------------------------------------
# isolation and weight
# ---------------------------------------------------------------------------


def test_a_live_server_address_in_the_bundle_is_refused(bundle, manifest):
    edit(bundle / "atlas.js", 'fetch("replay.json"', 'fetch("http://127.0.0.1:8000/replay.json"')
    messages = blockers(run(bundle, manifest), "isolation")
    assert any("loopback" in m for m in messages)


def test_an_operator_route_in_the_bundle_is_refused(bundle, manifest):
    edit(bundle / "atlas.js", 'fetch("replay.json"', 'fetch("/ops/alpha"')
    assert any("operator route" in m for m in blockers(run(bundle, manifest), "isolation"))


def test_a_third_party_url_is_refused(bundle, manifest):
    edit(bundle / "index.html", "<body>", '<body><script src="https://cdn.example.com/a.js"></script>')
    assert any("cdn.example.com" in m for m in blockers(run(bundle, manifest), "isolation"))


def test_the_form_endpoint_is_the_one_permitted_off_bundle_address(bundle, manifest):
    edit(bundle / "index.html", 'data-endpoint=""', 'data-endpoint="https://tally.so/r/abc123"')
    assert blockers(run(bundle, manifest), "isolation") == []


def test_the_svg_namespace_url_is_not_a_fetch(bundle, manifest):
    """The favicon is an inline SVG data URI carrying an xmlns declaration.

    It is a namespace name, not an address, and nothing requests it.
    """
    assert "www.w3.org" in (bundle / "index.html").read_text(encoding="utf-8")
    assert blockers(run(bundle, manifest), "isolation") == []


def test_the_weight_gate_is_measured_on_the_wire(bundle, manifest):
    findings = [f for f in run(bundle, manifest) if f.check == "weight"]
    assert len(findings) == 1
    assert findings[0].level == check_poster.NOTE
    assert "gzipped" in findings[0].message


def test_an_oversized_bundle_is_refused(bundle, manifest):
    # Incompressible, so gzip cannot rescue it: exactly the shape of an
    # unoptimised texture or a video someone dropped in.
    (bundle / "textures" / "plain.jpg").write_bytes(random.Random(7).randbytes(2 * 1024 * 1024))
    assert any("MB gzipped" in m for m in blockers(run(bundle, manifest), "weight"))
