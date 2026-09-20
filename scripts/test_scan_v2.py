"""Unit tests for scan_portals v2 (workplace classifier + grading) and the
scan_linkedin_guest parsers. Run:  python -m unittest test_scan_v2 -v
"""
import json
import os
import unittest

import scan_portals as sp

LOC_CFG = {
    "local_cities": ["gardena", "torrance", "el segundo", "hawthorne", "inglewood",
                     "carson", "long beach", "los angeles", "santa monica", "south bay"],
    "local_borderline": ["irvine", "orange county", "anaheim"],
}
US = ["united states", "u.s.", "remote us", "usa", "california", "new york", "texas",
      "los angeles", "hawthorne", "irvine", "gardena"]
NON_US = ["india", "london", "united kingdom", " uk", "canada", "toronto", "germany"]

SC = {
    "tracks": {
        "entry_cyber": ["soc analyst", "security analyst", "security operations"],
        "it_support": ["it support", "help desk"],
    },
    "bonus": {
        "claude_code": ["claude"],
        "ai_adoption": ["ai adoption"],
        "consulting": ["consultant"],
        "entry_signal": ["entry level", "junior", "tier 1"],
        "ca_proximity": ["gardena", "los angeles"],  # deprecated, must be ignored by v2
    },
    "drop": {
        "company_blocklist": ["turing"],
        "weapons_companies": ["anduril", "palantir", "lockheed", "general atomics"],
        "weapons_desc_patterns": ["munition", "missile", "warhead", "air dominance",
                                  "weapon system", "targeting system"],
        "clearance_patterns": ["ts/sci", "top secret"],
        "physical_security_desc_patterns": ["executive protection", "protective intelligence",
                                            "guard card", "post orders", "gsoc",
                                            "travel security and risk", "alarm monitoring"],
        "years_gate": 4,
        "pay_floor": 73000,
    },
    "pay_great": 85000,
    "pay_ok": 73000,
}


def job(loc="", desc="", wp_hint=None, title="Security Analyst", company="acme"):
    return {"id": "1", "title": title, "location": loc, "url": "", "updated": "",
            "board": "test", "company": company, "desc": desc, "wp_hint": wp_hint}


def classify(loc="", desc="", wp_hint=None):
    return sp.classify_workplace(job(loc=loc, desc=desc, wp_hint=wp_hint), LOC_CFG)


def keep(loc="", desc="", wp_hint=None, hybrid_ok=True):
    wp, tier = classify(loc, desc, wp_hint)
    return sp.keep_by_workplace(wp, tier, loc.lower(), US, NON_US, hybrid_ok)[0]


class TestClassifyWorkplace(unittest.TestCase):
    def test_remote_us(self):
        self.assertEqual(classify("Remote - US")[0], "remote")

    def test_terse_local_city_is_onsite_local(self):
        wp, tier = classify("Torrance, CA")
        self.assertEqual((wp, tier), ("onsite", "core"))

    def test_gardena_terse(self):
        wp, tier = classify("Gardena, California")
        self.assertEqual((wp, tier), ("onsite", "core"))

    def test_onsite_nonlocal_city(self):
        wp, tier = classify("New York, NY")
        self.assertEqual((wp, tier), ("onsite", ""))

    def test_pure_country_is_unknown(self):
        self.assertEqual(classify("United States")[0], "unknown")

    def test_empty_is_unknown(self):
        self.assertEqual(classify("")[0], "unknown")

    def test_hybrid_string_local(self):
        wp, tier = classify("Hybrid - Los Angeles")
        self.assertEqual((wp, tier), ("hybrid", "core"))

    def test_carson_city_guard(self):
        wp, tier = classify("Carson City, NV")
        self.assertEqual(tier, "")
        self.assertEqual(wp, "onsite")

    def test_carson_ca_is_local(self):
        self.assertEqual(classify("Carson, CA")[1], "core")

    def test_borderline(self):
        self.assertEqual(classify("Irvine, CA")[1], "borderline")

    def test_wp_hint_beats_string(self):
        # Ashby isRemote / Lever workplaceType style hint wins over a city string
        self.assertEqual(classify("Los Angeles, CA", wp_hint="remote")[0], "remote")
        self.assertEqual(classify("Remote", wp_hint="hybrid")[0], "hybrid")

    def test_desc_fallback_hybrid(self):
        self.assertEqual(classify("Los Angeles metro area is preferred",
                                  desc="This is a hybrid role, 3 days in office.")[0], "hybrid")

    def test_desc_fallback_onsite(self):
        self.assertEqual(classify("Los Angeles metro area is preferred",
                                  desc="This position is fully on-site.")[0], "onsite")


class TestKeepByWorkplace(unittest.TestCase):
    def test_remote_kept(self):
        self.assertTrue(keep("Remote - US"))

    def test_torrance_onsite_kept(self):          # the v1 terse-city drop, fixed
        self.assertTrue(keep("Torrance, CA"))

    def test_ny_onsite_dropped(self):              # the v1 leak, fixed
        self.assertFalse(keep("New York, NY"))

    def test_unknown_country_kept(self):
        self.assertTrue(keep("United States"))

    def test_hybrid_local_kept(self):
        self.assertTrue(keep("Hybrid - Los Angeles"))

    def test_hybrid_nonlocal_dropped(self):
        self.assertFalse(keep("Austin, TX", wp_hint="hybrid"))

    def test_hybrid_disabled(self):
        self.assertFalse(keep("Hybrid - Los Angeles", hybrid_ok=False))

    def test_non_us_dropped(self):
        self.assertFalse(keep("London"))

    def test_remote_non_us_dropped(self):
        self.assertFalse(keep("Remote - Canada"))

    def test_carson_city_dropped(self):
        self.assertFalse(keep("Carson City, NV"))


class TestGradeJob(unittest.TestCase):
    def graded(self, **kw):
        j = job(**kw)
        wp, tier = sp.classify_workplace(j, LOC_CFG)
        j["workplace"], j["local_tier"] = wp, tier
        return j, sp.grade_job(j, SC)

    def test_remote_bonus_only_for_remote_workplace(self):
        # JD merely MENTIONING remote must not fire the bonus (v1 over-fire)
        _, (_, _, tags, _) = self.graded(loc="Torrance, CA",
                                         desc="security analyst; our remote offices vary")
        self.assertNotIn("remote", tags)
        _, (_, _, tags2, _) = self.graded(loc="Remote - US", desc="security analyst")
        self.assertIn("remote", tags2)

    def test_local_onsite_bonus_and_tag(self):
        _, (_, _, tags, _) = self.graded(loc="Gardena, California", desc="security analyst")
        self.assertIn("CA-local", tags)
        self.assertIn("wp:onsite", tags)

    def test_borderline_tag(self):
        _, (_, _, tags, _) = self.graded(loc="Irvine, CA", desc="security analyst")
        self.assertIn("distance-check-required", tags)

    def test_wp_tag_always_present(self):
        _, (_, _, tags, _) = self.graded(loc="United States", desc="security analyst")
        self.assertTrue(any(t.startswith("wp:") for t in tags))

    def test_title_track_fit_reaches_A(self):
        # Real fit: track keyword in the TITLE + entry + local + good pay
        _, (g, score, tags, reasons) = self.graded(
            title="Junior Security Analyst", loc="Torrance, CA",
            desc="entry level security operations role. $85,000 per year")
        self.assertEqual(g, "A")
        self.assertIn("entry-cyber", tags)

    def test_desc_only_track_capped_B(self):
        # Keyword-soup guard: JD text mentions a track but the TITLE shows no fit
        # -> may score high on bonuses but can never be graded A (v3 gate).
        _, (g, score, tags, reasons) = self.graded(
            title="Operations Associate", loc="Remote - US",
            desc="junior role. our platform serves soc analyst teams doing security "
                 "operations with claude and ai adoption consultant workflows. $90,000")
        self.assertNotEqual(g, "A")
        self.assertTrue(any("JD text only" in r or "no title-level" in r for r in reasons),
                        f"expected a v3 cap reason, got {reasons}")

    def test_physical_security_jd_in_disguise_dropped(self):
        # The live 2026-07-03 catch: cyber-sounding title, GSOC/protective-intel body
        _, (g, _, tags, _) = self.graded(
            title="Strategic Security Analyst", loc="Costa Mesa, CA",
            desc="rotate through travel security and risk advisory, gsoc monitoring, "
                 "threat intelligence, and protective intelligence teams. $80,000")
        self.assertEqual(g, "F")
        self.assertIn("physical-security", tags)

    def test_weapons_company_dropped(self):
        # Values exclusion 2026-07-07: weapons makers + targeting software.
        # Even a neutral title at the company itself is out.
        _, (g, _, tags, _) = self.graded(
            title="Data Analyst", company="Anduril Industries", loc="Costa Mesa, CA",
            desc="entry level analytics role. $90,000")
        self.assertEqual(g, "F")
        self.assertIn("weapons-defense", tags)

    def test_weapons_company_in_jd_dropped(self):
        # Staffing post recruiting FOR a weapons maker — company field looks clean
        _, (g, _, tags, _) = self.graded(
            title="Junior Security Analyst", company="Acme Staffing", loc="Remote - US",
            desc="our client lockheed martin seeks a security analyst. entry level. $85,000")
        self.assertEqual(g, "F")
        self.assertIn("weapons-defense", tags)

    def test_weapons_program_jd_dropped(self):
        # Neutral title, weapons-program body (>=2 distinct patterns)
        _, (g, _, tags, _) = self.graded(
            title="Data Analyst", company="acme", loc="Costa Mesa, CA",
            desc="support air dominance programs; analyze weapon system telemetry "
                 "and missile test data. entry level. $95,000")
        self.assertEqual(g, "F")
        self.assertIn("weapons-defense", tags)

    def test_single_weapons_mention_not_dropped(self):
        # One pattern alone must not trip it (cyber JDs can mention one legitimately)
        _, (g, _, tags, _) = self.graded(
            title="SOC Analyst", company="acme", loc="Remote - US",
            desc="cyber security operations, SIEM triage; we protect customers from "
                 "attacks on missile-adjacent supply chains. entry level. $85,000")
        self.assertNotEqual(g, "F")
        self.assertNotIn("weapons-defense", tags)

    def test_single_physical_mention_not_dropped(self):
        # A cyber JD may mention ONE physical pattern legitimately
        _, (g, _, tags, _) = self.graded(
            title="SOC Analyst", loc="Remote - US",
            desc="cyber security operations, SIEM triage. our gsoc team partners "
                 "with facilities. entry level. $85,000")
        self.assertNotEqual(g, "F")

    def test_pay_floor_still_drops(self):
        _, (g, _, tags, _) = self.graded(
            title="IT Support Technician", loc="Gardena, California",
            desc="help desk role. $20 per hour")
        self.assertEqual(g, "F")
        self.assertIn("low-pay", tags)


class TestLinkedInParsers(unittest.TestCase):
    """Parser tests against raw fixtures captured from the live guest endpoints.
    Skipped automatically until the fixtures exist."""
    FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

    def _read(self, name):
        p = os.path.join(self.FIX, name)
        if not os.path.exists(p):
            self.skipTest(f"fixture {name} not captured yet")
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()

    def test_parse_cards(self):
        page = self._read("li_search.html")
        import scan_linkedin_guest as li
        cards = li.parse_cards(page)
        self.assertGreater(len(cards), 3)
        for c in cards:
            self.assertTrue(c["job_id"].isdigit())
            self.assertTrue(c["title"])
            self.assertTrue(c["company"])
            self.assertIn("linkedin.com/jobs/view/", c["url"])

    def test_parse_detail(self):
        page = self._read("li_view.html")
        import scan_linkedin_guest as li
        desc = li.parse_detail(page)
        self.assertGreater(len(desc), 200)
        self.assertNotIn("<div", desc)


if __name__ == "__main__":
    unittest.main()
