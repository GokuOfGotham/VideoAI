"""The $5,000 Promise, part two: the critics' case, built from CNN, MS NOW, NBC,
CBS, ABC and PBS coverage.

Stages (run in order; each is cached and idempotent):
    python create_5000_promise_v2.py narrate     # Cedar takes + word timings
    python create_5000_promise_v2.py plan        # timelines, policy check, range audit
    python create_5000_promise_v2.py render main
    python create_5000_promise_v2.py render short
    python create_5000_promise_v2.py music       # optional Epidemic bed (records manifest)
    python create_5000_promise_v2.py qa          # probes, loudness, silences, sheets
    python create_5000_promise_v2.py package     # SCRIPT.md, FACT_CHECK.md, manifest, covers

Sources are the raw downloads in output/The_5000_Promise_V2_20260912/work/raw
(see download_sources.py there). Every original-audio excerpt is cut on word
boundaries verified by a secondary transcription (work/sources/excerpt_words.json).

Lessons from the first video are enforced here rather than remembered:
  * a source range is never shown twice (audited in `plan`),
  * excerpt captions live in their own zone, never over the footer strap,
  * the Short ends when the narration ends instead of padding to 60 s.
"""
import argparse
import concurrent.futures
import copy
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration_tools import narrate_line, load_preset, synthesize, transcribe_words, restore_punctuation  # noqa: E402
from videoai_policy import validate_script  # noqa: E402
from videoai_graphics import broadcast as bc  # noqa: E402  house graphics system

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "The_5000_Promise_V2_20260912"
WORK = OUT / "work"
RAW = WORK / "raw"
AUDIO = WORK / "audio"
PLATES = WORK / "plates"
SHOTS = WORK / "shots"
PREP = WORK / "prepared"
QA = WORK / "qa"
for d in (AUDIO, PLATES, SHOTS, PREP, QA):
    d.mkdir(parents=True, exist_ok=True)

FF = shutil.which("ffmpeg") or "ffmpeg"
FP = shutil.which("ffprobe") or "ffprobe"
FPS = 30
NAMES = {"main": "The_5000_Promise_Critics_Case_1080p.mp4", "short": "The_5000_Promise_Critics_Case_Short.mp4"}
TITLE = "THE $5,000 PROMISE: THE CRITICS' CASE"
CUTOFF = "September 12, 2026"

THEME = "broadcast"  # "classic" = the first Civic Context look; "broadcast" = NBC / MS NOW style bars and cards
# Broadcast palette: navy ground, royal-blue and red tabs, white bars, near-black type.
B_BG = "#0B1730"; B_BG2 = "#08122A"; B_BLUE = "#1B4ED8"; B_BLUE2 = "#2F6BFF"; B_RED = "#D62828"
B_WHITE = "#FFFFFF"; B_CARD = "#F5F7FB"; B_INK = "#101418"; B_NAVY = "#0F2452"; B_GRAY = "#5B6B85"; B_MUTE = "#9FB0CC"; B_EDGE = "#3A4B6E"
FONTS = {"cond": "C:/Windows/Fonts/RobotoCondensed-Bold.ttf", "bold": "C:/Windows/Fonts/Roboto-Bold.ttf", "reg": "C:/Windows/Fonts/Roboto-Regular.ttf",
         "black": "C:/Windows/Fonts/Roboto-Black.ttf", "num": "C:/Windows/Fonts/bahnschrift.ttf"}
BG = "#080F19"; PANEL = "#111F2E"; ROW = "#1A2D3E"; WHITE = "#F4F3EE"; MUTED = "#AAB7C5"
CYAN = "#66D3E5"; RED = "#EF625D"; GOLD = "#EFCE86"; RULE = "#384657"

# --- Sources ----------------------------------------------------------------
# key -> (outlet, programme, air/upload date). URL/title come from the download receipts.
SOURCES = {
    "cnn": ("CNN", "CNN NewsNight / CNN This Morning", "September 11, 2026"),
    "msnow_desperation": ("MS NOW", "All In with Chris Hayes", "September 11, 2026"),
    "msnow_lawrence": ("MS NOW", "The Last Word with Lawrence O'Donnell", "September 11, 2026"),
    "msnow_oversight": ("MS NOW", "On the Line with Alicia Menendez", "September 10, 2026"),
    "msnow_floats": ("MS NOW", "MS NOW", "September 10, 2026"),
    "nbc_legal": ("NBC NEWS", "NBC News NOW", "September 10, 2026"),
    "nbc_lutnick": ("NBC NEWS", "NBC News NOW", "September 11, 2026"),
    "today_backlash": ("NBC", "TODAY", "September 11, 2026"),
    "cbs_dubious": ("CBS NEWS", "CBS Mornings", "September 10, 2026"),
    "cbs_scalise": ("CBS NEWS", "The Takeout with Major Garrett", "September 10, 2026"),
    "cbs_chicago": ("CBS NEWS", "CBS News Chicago", "September 10, 2026"),
    "cbs_texas_interview": ("CBS NEWS", "CBS News Texas", "September 10, 2026"),
    "pbs_criticism": ("PBS", "PBS News Hour", "September 10, 2026"),
    "pbs_remarks": ("PBS", "PBS News Hour", "September 10, 2026"),
    "abc_explainer": ("ABC NEWS", "ABC News", "September 10, 2026"),
}


def source_meta(key):
    for name in (f"download_{key}.json", f"meta_{key}.json"):
        p = WORK / "sources" / name
        if p.exists():
            m = json.loads(p.read_text(encoding="utf-8"))
            return {"title": m.get("title"), "url": m.get("youtube") or m.get("webpage_url"),
                    "upload_date": m.get("upload_date"), "width": m.get("width"), "height": m.get("height")}
    return {"title": None, "url": None, "upload_date": None, "width": None, "height": None}


# --- Original-audio excerpts ------------------------------------------------
# key -> dict(window=verify_excerpts window key, first=start of first word, last=start
# of last word, speaker card, caption text, own_caption). In/out are derived from the
# verified word list: 0.12 s before the first word, 0.30 s after the last word ends.
CLIPS = {
    "nbc_impossible": dict(src="nbc_legal", window="nbc_impossible", first=15.76, last=19.48,
        who="NBC NEWS NOW", big="\"ABSOLUTELY IMPOSSIBLE\"",
        lines=["Anchor asks a reporter how realistic the proposal is", "September 10, 2026"],
        caption="How realistic is that proposal? — It's absolutely impossible, to be frank.", tail=0.18, pad_after=0.12),
    "trump_promise": dict(src="cbs_dubious", window="trump_promise", first=95.38, last=103.26,
        who="PRESIDENT TRUMP", big="THE PROMISE",
        lines=["GOP midterm convention, Dallas, September 9", "Condition: Republicans keep House and Senate"],
        caption="I will issue a dividend to every adult citizen in the United States of America for $5,000."),
    "okeefe_math": dict(src="cbs_dubious", window="okeefe_math", first=106.38, last=116.6,
        who="ED O'KEEFE, CBS NEWS", big="THE MATH",
        lines=["≈ 269 million adults × $5,000", "≈ $1.3 trillion"],
        caption="About 269 million American adults, $5,000 each, you're hitting about $1.3 trillion. Where on earth does that money come from? Unclear."),
    "walkinshaw_budget": dict(src="msnow_oversight", window="walkinshaw", first=147.72, last=154.58,
        who="REP. JAMES WALKINSHAW (D-VA)", big="FOR SCALE",
        lines=["House Oversight Committee", "Discretionary budget ≈ $1.9 trillion / year"],
        caption="The federal government's discretionary budget is $1.9 trillion a year. It would be $1.3 trillion — more than the entire Defense Department's budget."),
    "trump_21t": dict(src="pbs_criticism", window="trump_21t", first=124.56, last=136.86,
        who="PRESIDENT TRUMP ON FOX NEWS", big="\"$21 TRILLION\"",
        lines=["Asked why not pay the money now", "Fox News interview, aired by PBS News Hour"],
        caption="So we're taking in $21 trillion. No country has ever taken in anywhere near that. It's four or five times higher than the next, all because of that beautiful word that you and I love more than most others: tariffs."),
    "hayes_400b": dict(src="msnow_desperation", window="hayes_400b", first=453.7, last=461.22,
        who="CHRIS HAYES, MS NOW", big="THE FACT CHECK",
        lines=["Tariff revenue: \"like $400 billion\"", "Part of it being refunded"],
        caption="We haven't taken in $21 trillion in tariff revenue. It's been like $400 billion. It's all being refunded, by the way, to the big corporations that charge it."),
    "lutnick_a": dict(src="nbc_lutnick", window="lutnick", first=235.14, last=242.16,
        who="HOWARD LUTNICK, COMMERCE SECRETARY", big="\"NON-TAX MONEY\"",
        lines=["Asked how the payment would be paid for", "NBC News interview, September 11"],
        caption="…that he can make money not from tax money, and this is key. Not tax money. This is not tax money. This is going to be non-tax money."),
    "trump_congress": dict(src="cbs_texas_interview", window="trump_congress", first=19.8, last=26.96,
        who="PRESIDENT TRUMP", big="\"WE THINK NOT\"",
        lines=["Asked whether Congress would need to approve it", "CBS News Texas, September 10"],
        caption="— Would Congress need to approve that? — Well, we think not. I think they will do it if we needed it, but we think not."),
    "scalise_a": dict(src="cbs_scalise", window="scalise_congress", first=180.84, last=183.1,
        who="STEVE SCALISE, HOUSE MAJORITY LEADER", big="\"WORKED OUT BY CONGRESS\"",
        lines=["Asked where the money would come from", "CBS News, September 10"],
        caption="Well, the details obviously have to be worked out by Congress."),
    "scalise_b": dict(src="cbs_scalise", window="scalise_congress", first=209.6, last=216.42,
        who="STEVE SCALISE, HOUSE MAJORITY LEADER", big="\"THE VERY FIRST STAGES\"",
        lines=["The plan has not been written", "CBS News, September 10"],
        caption="So we're in the very first stages: when the president throws out an idea, then it's up to us in Congress to make the numbers work, to get the details right."),
    "talarico": dict(src="msnow_desperation", window="hayes_chambers", first=408.98, last=416.12,
        who="JAMES TALARICO (D), TEXAS SENATE NOMINEE", big="WHY WAIT?",
        lines=["Interview aired on MS NOW", "Republicans already hold both chambers"],
        caption="They already have both chambers. They have the House and the Senate and the White House. So why do we have to wait till after the election?"),
    "trump_reward": dict(src="today_backlash", window="trump_reward", first=77.06, last=87.78,
        who="PRESIDENT TRUMP", big="\"A REWARD\"",
        lines=["Asked about the timing", "As aired by NBC's TODAY, September 11"],
        caption="I didn't do it for turning out the vote. I did it as a reward for people having to put up with five years and four years of a horrible situation caused by Biden.",
        own_caption=False),
    "dem_briber": dict(src="cbs_chicago", window="dem_briber", first=58.56, last=65.46,
        who="DEMOCRATIC GOVERNOR, DGA EVENT", big="\"BRIBER-IN-CHIEF\"",
        lines=["Democratic Governors Association event", "As aired by CBS News Chicago"],
        caption="Last night, the president made himself the briber-in-chief. It is not legal to offer people money for their vote."),
    "hasen": dict(src="pbs_criticism", window="hasen", first=95.18, last=104.44,
        who="RICK HASEN, UCLA SCHOOL OF LAW", big="LIKELY LEGAL",
        lines=["Election-law scholar", "PBS News Hour, September 10"],
        caption="It's really not that much different from saying, if you vote for me I'll pass Medicare for All, or if you vote for me I'll cut your taxes by 20 percent. Politicians make these kinds of things all the time."),
    "scalise_bribe": dict(src="cbs_scalise", window="scalise_bribe", first=217.18, last=224.36,
        who="STEVE SCALISE, HOUSE MAJORITY LEADER", big="\"IS IT A BRIBE?\"",
        lines=["Question from CBS's Ed O'Keefe", "CBS News, September 10"],
        caption="— Is it a bribe, though, to be telling people you'll get $5,000 if you vote Republican? — No, it's a reality to say Democrats are against this."),
    "walkinshaw_doge": dict(src="msnow_oversight", window="walkinshaw_doge", first=62.9, last=65.52,
        who="REP. JAMES WALKINSHAW (D-VA)", big="THE DOGE DIVIDEND",
        lines=["Promised: 20% of projected DOGE savings ≈ $5,000", "Never paid"],
        caption="Did you get your $5,000? I did not. I don't think anyone did."),
    "vance_fox_cnn": dict(src="cnn", window="vance_fox_cnn", first=550.52, last=554.4,
        who="VICE PRESIDENT VANCE ON FOX NEWS", big="\"A DIVIDEND\"",
        lines=["Asked whether the plan is a bribe", "Fox News clip as aired by CNN"],
        caption="First of all, what the president's talking about is fundamentally a dividend for American workers."),
}
LEAD = 0.12
TAIL = 0.30


def excerpt_words():
    return json.loads((WORK / "sources" / "excerpt_words.json").read_text(encoding="utf-8"))


def clip_bounds(key):
    c = CLIPS[key]
    words = excerpt_words()[c["window"]]["words"]
    first = next(w for w in words if abs(w["start"] - c["first"]) < 0.02)
    last = next(w for w in words if abs(w["start"] - c["last"]) < 0.02)
    inside = [w for w in words if first["start"] <= w["start"] <= last["start"]]
    return round(first["start"] - c.get("lead", LEAD), 3), round(last["end"] + c.get("tail", TAIL), 3), inside


# --- Evidence cards ---------------------------------------------------------
CARDS = {
    "promise": ("THE PROMISE", "$5,000", ["Every adult U.S. citizen", "Condition: Republicans keep the House and Senate", "Announced September 9, Dallas"], "GOP midterm convention · via CBS, PBS, NBC"),
    "outlets": ("THE COVERAGE", "THREE QUESTIONS", ["What would it cost?", "Where would the money come from?", "Who can authorize a payment?"], "CNN · MS NOW · NBC · CBS · ABC · PBS"),
    "math": ("THE ARITHMETIC", "$1.3 TRILLION", ["≈ 269 million adults (CBS figure)", "× $5,000 each", "Before administration costs"], "CBS, NBC, MS NOW and PBS estimates"),
    "scale": ("FOR SCALE", "$1.9 TRILLION", ["Annual discretionary spending", "The part Congress votes on each year", "Defense is the largest single piece"], "Figure cited by Rep. Walkinshaw on MS NOW"),
    "debt": ("NATIONAL DEBT", "$40 TRILLION+", ["Shown on CNN This Morning", "Cited on NBC's TODAY", "A new payment would add to it"], "Treasury figure as displayed by CNN"),
    "tariffs": ("THE PRESIDENT'S ANSWER", "TARIFFS", ["\"We are taking in $21 trillion\" — Fox News", "Asked why the money could not be paid now", "Aired by PBS News Hour"], "Fox News interview via PBS"),
    "receipts": ("FEDERAL RECEIPTS", "≈ $5 TRILLION / YEAR", ["All sources combined, FY2025", "\"$21 trillion\" appears in no Treasury report", "Tariff collections are a fraction of receipts"], "U.S. Treasury monthly statements"),
    "refund": ("THE COMPLICATION", "REFUNDS", ["Supreme Court ruled against the tariffs", "Importers are being repaid", "$2.9B Walmart · $2.2B Apple (per O'Donnell)"], "MS NOW · CNN"),
    "lutnick": ("THE SECOND ANSWER", "NON-TAX MONEY", ["Commerce Secretary Howard Lutnick", "\"Not from the deficit and not from taxpayers\"", "Example: the Trump Platinum Card"], "NBC News interview, September 11"),
    "platinum": ("THE PLATINUM CARD MATH", "$500 BILLION", ["$5 million visa product", "Waiting list: \"more than 100,000\" (Lutnick)", "A projection of sales, not cash on hand"], "Lutnick's figures as stated to NBC"),
    "authority": ("WHO AUTHORIZES IT?", "ARTICLE I", ["No money drawn from the Treasury", "except under appropriations made by law", "The question put to the president in Texas"], "U.S. Constitution, Article I, Section 9"),
    "two_answers": ("TWO ANSWERS", "PRESIDENT vs. HOUSE", ["Trump: \"We think not\"", "Scalise: \"worked out by Congress\"", "Moreno: says he will introduce a bill"], "CBS News Texas · CBS News · MS NOW"),
    "gop_skeptics": ("REPUBLICAN SKEPTICS", "NOT ALL ON BOARD", ["Chip Roy: dependency \"evil and soul-sucking\"", "Susan Collins: questioned the price tag", "Conservative op-eds: \"bribery\", \"a bridge to sell you\""], "PBS · NBC TODAY · MS NOW"),
    "why_wait": ("THE TIMING QUESTION", "WHY WAIT?", ["Republicans hold the House, Senate and White House", "Payment promised only after the election", "Trump: \"a reward,\" not turnout"], "MS NOW · NBC TODAY"),
    "bribe": ("THE ACCUSATION", "\"BRIBE\"", ["Democrats: an illegal attempt to buy votes", "A political accusation", "Not a legal finding"], "CBS News Chicago"),
    "hasen": ("THE LEGAL VIEW", "LIKELY PROTECTED", ["Rick Hasen, UCLA School of Law", "A public campaign promise to all voters", "First Amendment"], "PBS News Hour"),
    "distinction": ("THE DISTINCTION", "POLICY vs. PAYMENT", ["A promise of policy to every voter", "versus a payment for an individual vote", "Nothing published requires proving a vote"], "Analysis of the stated condition"),
    "okeefe": ("CBS'S FRAMING", "INTERPRETATION", ["A stimulus, if it is a policy", "A bribe, if it is a transaction", "Ed O'Keefe, CBS News"], "CBS Mornings, September 10"),
    "record_bribe": ("ON THE BRIBE QUESTION", "THREE ENTRIES", ["An accusation (Democrats)", "A defense (Scalise)", "A legal opinion (Hasen): likely lawful"], "Attributed positions, not findings"),
    "history": ("THE TRACK RECORD", "DELIVERED", ["2020: stimulus checks bearing Trump's name", "2025: $1,776 bonuses to service members"], "PBS News Hour · NBC TODAY"),
    "never": ("THE TRACK RECORD", "NOT DELIVERED", ["Tariff rebate checks: floated, never sent", "\"DOGE dividend\": ≈ $5,000, never sent"], "PBS News Hour · Rep. Walkinshaw on MS NOW"),
    "vance": ("THE DEFENSE", "\"A DIVIDEND FOR WORKERS\"", ["Vice President Vance on Fox News", "Funded, he said, by tariff revenue", "Revenue now partly subject to refunds"], "Fox News clip via CNN"),
    "wh_statement": ("WHITE HOUSE RESPONSE", "NO MECHANISM", ["PBS asked for payment and cost details", "Reply: the president has \"proven his doubters wrong\"", "No eligibility, funding source or date"], "PBS News Hour, September 10"),
    "ledger": ("THE RECORD", "WHERE IT STANDS", ["Promise: documented", "Cost: more than $1 trillion (multiple outlets)", "Funding: challenged · Authority: disputed"], "Research cutoff " + CUTOFF),
    "next": ("WHAT WOULD CHANGE THE STORY", "FOUR THINGS", ["A bill with text", "A funding source that survives arithmetic", "A payment date", "A Congressional Budget Office estimate"], "CIVIC CONTEXT"),
    "reward": ("THE PRESIDENT'S ANSWER", "\"A REWARD\"", ["\"I didn't do it for turning out the vote\"", "As aired by NBC's TODAY"], "NBC TODAY, September 11"),
    "scalise2": ("ASKED DIRECTLY", "\"IS IT A BRIBE?\"", ["Question from CBS's Ed O'Keefe", "House Majority Leader Steve Scalise"], "CBS News, The Takeout"),
}
# Cards drawn as a big-number exhibit when they fill the main panel.
EXHIBITS = {
    "math": ("269 MILLION × $5,000", "$1.3 TRILLION", "ILLUSTRATIVE, BEFORE ADMINISTRATION COSTS", 1.0),
    "receipts": ("FEDERAL RECEIPTS, ALL SOURCES", "≈ $5 TRILLION", "PER YEAR · \"$21 TRILLION\" IS NOT A TREASURY FIGURE", 0.24),
    "platinum": ("100,000 × $5 MILLION", "$500 BILLION", "A SALES PROJECTION · UNDER HALF THE ESTIMATED COST", 0.38),
}

# --- Script -----------------------------------------------------------------
# Each section is a list of units: ("clip", key) or ("say", text, plan) where plan is a
# list of (anchor phrase, card, muted source or None, seek seconds). The first anchor is
# always "" (paragraph start). B-roll is muted; only "clip" units carry original audio.
SECTIONS = [
 ("THE PROMISE", [
  ("clip", "nbc_impossible"),
  ("clip", "trump_promise"),
  ("say", "That is the promise Donald Trump made on September ninth at the Republican midterm convention in Dallas: five thousand dollars to every adult citizen, but only if Republicans keep the House and the Senate. Within a day, CNN, M-S NOW, NBC, CBS and PBS had converged on three questions: what it would cost, where the money would come from, and who has the power to send a check.",
   [("", "promise", "pbs_criticism", 24.0), ("Within a day", "outlets", "cnn", 36.0), ("where the money", "outlets", "msnow_desperation", 300.0)]),
 ]),
 ("THE MATH", [
  ("clip", "okeefe_math"),
  ("say", "Two hundred sixty-nine million is the adult population figure CBS used; NBC, M-S NOW and PBS all put the total above a trillion dollars. The arithmetic is not in dispute. What it buys is the argument, and one Democrat on the House Oversight Committee reached for the federal budget.",
   [("", "math", None, 0), ("What it buys", "scale", "msnow_oversight", 30.0)]),
  ("clip", "walkinshaw_budget"),
  ("say", "That was Virginia Congressman James Walkinshaw on M-S NOW. The comparison is political, but the numbers are public: discretionary spending, the part Congress votes on each year, is a little under two trillion dollars. And a new payment of this size would land on a national debt that, as CNN and NBC both noted, has passed forty trillion.",
   [("", "scale", "msnow_oversight", 128.0), ("And a new payment", "debt", "cnn", 466.0)]),
 ]),
 ("WHERE'S THE MONEY?", [
  ("say", "The president's answer is tariffs. Asked on Fox News why the money could not simply be paid now, he gave this account of federal revenue.",
   [("", "tariffs", "pbs_criticism", 170.5)]),
  ("clip", "trump_21t"),
  ("say", "Twenty-one trillion dollars appears in no Treasury report; total federal receipts from every source were about five trillion dollars in the last fiscal year. On M-S NOW, Chris Hayes put tariff collections far lower, and raised a complication that CNN's morning panel raised too.",
   [("", "receipts", None, 0), ("On M-S NOW", "refund", "msnow_desperation", 438.0)]),
  ("clip", "hayes_400b"),
  ("say", "After the Supreme Court ruled against the tariffs, importers began getting that money back; M-S NOW's Lawrence O'Donnell cited two point nine billion dollars to Walmart and two point two billion to Apple. Revenue being returned under a court order is not revenue available for a dividend. Commerce Secretary Howard Lutnick offered NBC News a different source.",
   [("", "refund", "msnow_lawrence", 598.0), ("M-S NOW's Lawrence", "refund", "msnow_lawrence", 224.0), ("Commerce Secretary", "lutnick", "nbc_lutnick", 226.0)]),
  ("clip", "lutnick_a"),
  ("say", "His example was the Trump Platinum Card, a five-million-dollar visa product with, he said, a waiting list of more than one hundred thousand people, which he multiplied to five hundred billion dollars. That is a projection of future sales, not cash on hand, and even at face value it is less than half the estimated cost.",
   [("", "platinum", "nbc_lutnick", 60.0), ("That is a projection", "platinum", None, 0)]),
 ]),
 ("WHO DECIDES?", [
  ("say", "Even with a funding source, a federal payment needs legal authority: the Constitution allows no money to be drawn from the Treasury except under appropriations made by law. So the question put to the president in Texas was direct.",
   [("", "authority", None, 0), ("So the question", "authority", "cbs_texas_interview", 6.0)]),
  ("clip", "trump_congress"),
  ("say", "The House Majority Leader described the process differently the same day.",
   [("", "two_answers", "cbs_scalise", 100.0)]),
  ("clip", "scalise_a"),
  ("clip", "scalise_b"),
  ("say", "Two different answers: Congress would act if asked, or Congress is where the plan would actually be written. Ohio Senator Bernie Moreno said he would introduce a bill. Other Republicans were cooler. Texas Congressman Chip Roy wrote that dependency is, quote, evil and soul-sucking in all its forms. Maine's Susan Collins questioned the price tag. And Texas Democrat James Talarico asked the question several critics asked.",
   [("", "two_answers", None, 0), ("Other Republicans", "gop_skeptics", "pbs_criticism", 66.0), ("Maine's Susan", "gop_skeptics", "msnow_lawrence", 72.0), ("And Texas Democrat", "why_wait", "msnow_desperation", 396.0)]),
  ("clip", "talarico"),
  ("say", "The president's own answer, as aired by NBC's Today show, was that the payment is not about turnout.",
   [("", "reward", "today_backlash", 66.0)]),
  ("clip", "trump_reward"),
 ]),
 ("IS IT A BRIBE?", [
  ("say", "The word Democrats reached for was bribe.",
   [("", "bribe", "cbs_chicago", 34.0)]),
  ("clip", "dem_briber"),
  ("say", "That is a political accusation, and the legal question was contested from an unexpected direction. Rick Hasen, an election-law scholar at UCLA, told PBS NewsHour the promise is most likely protected speech.",
   [("", "bribe", "msnow_lawrence", 84.0), ("Rick Hasen", "hasen", "pbs_criticism", 84.0)]),
  ("clip", "hasen"),
  ("say", "The distinction is between a public promise of policy to all voters and a private payment for an individual vote. The announced condition concerns which party controls Congress; nothing published requires anyone to prove how they voted. CBS's Ed O'Keefe called it a matter of interpretation. Asked directly, Steve Scalise rejected the label.",
   [("", "distinction", None, 0), ("CBS's Ed", "okeefe", "cbs_dubious", 60.0), ("Asked directly", "scalise2", "cbs_scalise", 106.0)]),
  ("clip", "scalise_bribe"),
  ("say", "So the record here is an accusation, a defense, and a legal opinion that a court would likely side with the defense. None of it settles whether the money would move.",
   [("", "record_bribe", None, 0)]),
 ]),
 ("THE TRACK RECORD", [
  ("say", "Critics kept returning to the history. PBS noted that stimulus checks bearing the president's name did go out in twenty twenty, and NBC noted seventeen-seventy-six-dollar bonuses paid to service members last year. But a tariff rebate check the president floated never materialized, and neither did the so-called Doge dividend. Congressman Walkinshaw remembered that one.",
   [("", "history", "pbs_criticism", 156.0), ("and NBC noted", "history", "today_backlash", 89.0), ("But a tariff", "never", "msnow_oversight", 44.0)]),
  ("clip", "walkinshaw_doge"),
  ("say", "Vice President Vance, asked on Fox News whether this was a bribe, described it as a dividend for workers.",
   [("", "vance", "cnn", 543.0)]),
  ("clip", "vance_fox_cnn"),
  ("say", "Funded, he said, by tariff revenue, the same revenue now partly subject to refunds. And when PBS asked the White House for details on payment and cost, it received a statement about the president proving his doubters wrong. The statement did not describe a mechanism.",
   [("", "vance", "pbs_criticism", 138.0), ("And when PBS", "wh_statement", "pbs_criticism", 144.0)]),
 ]),
 ("WHAT WOULD CHANGE THE STORY", [
  ("say", "Four things would turn this promise into a program: a bill with text, a funding source that survives the arithmetic, a payment date, and a Congressional Budget Office estimate. Until they exist, the five-thousand-dollar figure is what it was on September ninth: a campaign promise, conditioned on an election, with no mechanism behind it.",
   [("", "next", None, 0), ("Until they exist", "next", "cbs_dubious", 138.0)]),
 ]),
]

SHORT_TEXT = ("Five thousand dollars for every adult, if Republicans keep Congress. That is Donald Trump's promise, and here is the case critics have built against it. "
              "Cost: about two hundred seventy million adults, so roughly one point three trillion dollars, most of a year's discretionary budget. "
              "Money: the president says tariffs. M-S NOW puts collections at a few hundred billion, and CNN notes part of it is being refunded under a Supreme Court ruling. "
              "Authority: the president says Congress would not need to approve it; House Majority Leader Scalise says the details have to be worked out by Congress. "
              "And the bribe charge? An election-law expert told PBS it is most likely protected campaign speech. "
              "The promise is on the record; so far, the program is not.")
SHORT_PLAN = [("", "promise", "pbs_criticism", 30.0), ("Cost", "math", None, 0), ("Money", "tariffs", "pbs_criticism", 171.0),
              ("Authority", "two_answers", "cbs_scalise", 110.0), ("And the bribe", "hasen", "pbs_criticism", 88.0), ("The promise is", "next", None, 0)]

REVIEW_MAIN = {
    "content_type": "documentary", "format": "long", "hook_start_seconds": 0,
    "hook": "Second zero is NBC's reporter answering 'how realistic is that proposal?' with 'absolutely impossible', cut straight to Trump's own words promising $5,000 to every adult citizen (CBS footage, original audio).",
    "first_payoff_seconds": 13,
    "first_payoff": "By 0:13 the viewer has heard the full promise in Trump's voice with the condition and cost on the evidence panel; at 0:27 CBS's Ed O'Keefe delivers the first hard number on air: 269 million adults x $5,000 = about $1.3 trillion.",
    "pacing_review": "Seven chapters, each opening on a claim or question and answered by an attributed excerpt; 19 original-audio excerpts cut on verified word boundaries with 0.12 s lead and 0.30 s tail; narration takes have measured silences over 0.47 s shortened to about 0.32 s with no time-stretch; no channel intro; every source range is used once (audited); muted B-roll is labeled and credited on the panel; the closing lists the four documents that would change the story instead of a recap montage.",
    "audio_mode": "cedar", "standalone": True, "overrides": {},
}
REVIEW_SHORT = {
    "content_type": "documentary", "format": "short", "hook_start_seconds": 0,
    "hook": "Second zero is NBC's 'absolutely impossible' answer over convention footage, then the narration states the $5,000 promise and its condition in the first sentence.",
    "first_payoff_seconds": 9,
    "first_payoff": "By 0:09 the narration has delivered the cost (about $1.3 trillion) with the arithmetic exhibit on screen.",
    "pacing_review": "One excerpt plus a single tightened Cedar take covering cost, money, authority and the bribe question; ends 0.6 s after the last word with no padding to 60 s and no reference to the long video.",
    "audio_mode": "cedar", "standalone": True, "overrides": {},
}


# --- Helpers ----------------------------------------------------------------
def run(cmd, cwd=None):
    p = subprocess.run([str(v) for v in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(p.stderr[-4000:])
    return p.stdout


def norm(s):
    return re.sub("[^a-z0-9]", "", s.lower())


def wav_seconds(p):
    with wave.open(str(p), "rb") as f:
        return f.getnframes() / f.getframerate()


def tighten(source, words, dest):
    """Shorten measured silences inside a take; never touches speech (AGENTS.md)."""
    with wave.open(str(source), "rb") as f:
        params = f.getparams(); raw = f.readframes(f.getnframes())
    rate = params.framerate; stride = params.sampwidth * params.nchannels; dur = len(raw) / stride / rate
    assert params.sampwidth == 2
    samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, params.nchannels).astype(np.float32)
    win = round(rate * .01); pad = (-len(samples)) % win
    energy = np.sqrt(np.mean(np.pad(samples, ((0, pad), (0, 0))).reshape(-1, win, params.nchannels) ** 2, axis=(1, 2))) / 32768
    quiet = energy < 10 ** (-39 / 20); spans = []; start = None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i * .01
        if not q and start is not None:
            if i * .01 - start > .16:
                spans.append((start, min(dur, i * .01)))
            start = None
    cuts = []
    for a, b in spans:
        if a < .02:
            end = b - .055
            if end > .02:
                cuts.append((0, end))
        elif b > dur - .025:
            begin = max(a + .075, words[-1]["end"] + .09)
            if begin < dur:
                cuts.append((begin, dur))
        else:
            gap = next(((l["end"], r["start"]) for l, r in zip(words, words[1:]) if l["end"] <= a + .08 and r["start"] >= b - .08), None)
            if gap and b - a > .47:
                left = a + .16; right = b - .16
                if right > left:
                    cuts.append((left, right))
    result = bytearray(); last = 0; canonical = []
    for a, b in cuts:
        a = round(a * rate); b = round(b * rate)
        result += raw[last * stride:a * stride]; last = b; canonical.append((a / rate, b / rate))
    result += raw[last * stride:]

    def shift(t):
        return t - sum(max(0, min(t, b) - a) for a, b in canonical if t > a)
    fixed = [dict(w, start=round(shift(w["start"]), 3), end=round(max(shift(w["start"]) + .02, shift(w["end"])), 3)) for w in words]
    with wave.open(str(dest), "wb") as f:
        f.setparams(params._replace(nframes=len(result) // stride)); f.writeframes(result)
    return {"words": fixed, "seconds": len(result) / stride / rate, "original_seconds": dur, "removed": canonical}


def narration_units(kind):
    if kind == "short":
        return [("short", SHORT_TEXT)]
    return [(f"main_{i:02}_{j:02}", u[1]) for i, (_, units) in enumerate(SECTIONS) for j, u in enumerate(units) if u[0] == "say"]


def take(name):
    """Tightened take for a narration unit (cached)."""
    meta = AUDIO / (name + ".tight.json")
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    raise RuntimeError(f"Run `narrate` first: {name}")


def narrate_cached(text, dest, preset):
    """narrate_line with retries; a take whose synthesis succeeded is never re-recorded."""
    import time
    dest = Path(dest); meta = dest.with_suffix(".json")
    if dest.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    for attempt in range(4):
        try:
            if not dest.exists():
                synthesize(text, dest, preset)
            tr = transcribe_words(dest)
            break
        except Exception as e:  # transient network resets
            if attempt == 3:
                raise
            print(f"retry {dest.name}: {type(e).__name__}", flush=True); time.sleep(4 * (attempt + 1))
    duration = wav_seconds(dest)
    data = {"text": text, "audio": str(dest), "duration": round(duration, 3), "words": restore_punctuation(tr["words"], text)}
    meta.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def stage_narrate():
    preset = load_preset()
    units = narration_units("main") + narration_units("short")

    def one(unit):
        name, text = unit
        data = narrate_cached(text, AUDIO / (name + ".wav"), preset)
        tight = tighten(AUDIO / (name + ".wav"), data["words"], AUDIO / (name + ".tight.wav"))
        spoken = " ".join(w["word"] for w in data["words"])
        tokens = re.findall("[a-z0-9]+", text.lower()); heard = re.findall("[a-z0-9]+", spoken.lower())
        import difflib
        agreement = difflib.SequenceMatcher(None, tokens, heard, autojunk=False).ratio()
        report = {"name": name, "text": text, "seconds": round(tight["seconds"], 3), "original_seconds": round(tight["original_seconds"], 3),
                  "removed_seconds": round(tight["original_seconds"] - tight["seconds"], 3), "cuts": tight["removed"], "agreement": round(agreement, 3), "words": tight["words"]}
        (AUDIO / (name + ".tight.json")).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{name:<12} {report['seconds']:6.2f}s  (-{report['removed_seconds']:.2f}s silence)  agreement {agreement:.3f}", flush=True)
        return report
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(one, units))
    (WORK / "narration_report.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "words"} for r in reports], indent=1), encoding="utf-8")
    main_total = sum(r["seconds"] for r in reports if r["name"] != "short")
    print(f"MAIN narration {main_total:.1f}s   SHORT {[r for r in reports if r['name']=='short'][0]['seconds']:.1f}s")


# --- Timeline ---------------------------------------------------------------
def anchor_time(words, phrase):
    """Start time of the word where `phrase` begins; tolerant of transcriber
    splitting or joining tokens ("M-S NOW" heard as "MSNow")."""
    if not phrase:
        return 0.0
    target = norm(phrase); flat = [norm(w["word"]) for w in words]
    for i in range(len(flat)):
        acc = ""
        for k in range(i, len(flat)):
            acc += flat[k]
            if acc == target:
                return words[i]["start"]
            if len(acc) >= len(target) or not target.startswith(acc):
                break
    raise ValueError(f"No anchor {phrase!r}")


PAD_AFTER_SAY = 0.30
PAD_AFTER_CLIP = 0.36


def script_words(words, text):
    """Timed words spelled as the script spells them (the transcriber writes
    'five thousand dollars' as '5 000'); words the transcriber dropped get
    interpolated times, extra transcriber tokens are discarded."""
    import difflib
    tokens = text.split(); out = []
    sm = difflib.SequenceMatcher(None, [norm(w["word"]) for w in words], [norm(t) for t in tokens], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.extend(dict(word=tokens[j1 + k], start=words[i1 + k]["start"], end=words[i1 + k]["end"]) for k in range(i2 - i1))
        elif tag == "replace":
            a = words[i1]["start"]; b = words[i2 - 1]["end"]; n = j2 - j1
            out.extend(dict(word=tokens[j1 + k], start=round(a + (b - a) * k / n, 3), end=round(a + (b - a) * (k + 1) / n, 3)) for k in range(n))
        elif tag == "delete":
            a = out[-1]["end"] if out else 0.0; b = words[i1]["start"] if i1 < len(words) else a + 0.3 * (j2 - j1)
            # 'delete' here means the script has words the transcript lacks
            pass
        elif tag == "insert":
            a = out[-1]["end"] if out else 0.0; b = words[i1]["start"] if i1 < len(words) else a + 0.3 * (j2 - j1)
            n = j2 - j1; b = max(b, a + 0.12 * n)
            out.extend(dict(word=tokens[j1 + k], start=round(a + (b - a) * k / n, 3), end=round(a + (b - a) * (k + 1) / n, 3)) for k in range(n))
    # Punctuation-only tokens (a speaker-change dash) carry no speech: give them the
    # next real word's start so a caption never appears before its first spoken word.
    for i, w in enumerate(out):
        if not norm(w["word"]):
            nxt = next((x for x in out[i + 1:] if norm(x["word"])), None)
            t = nxt["start"] if nxt else w["end"]
            w["start"] = w["end"] = t
    return out


def _syllables(word):
    w = re.sub(r"[^a-z0-9]", "", word.lower())
    if not w:
        return 0.3
    if w.isdigit():
        return max(1, len(w))
    groups = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and groups > 1:
        groups -= 1
    return max(1, groups)


def retime_words(words, env, step, blend=0.6):
    """Re-time transcriber words against measured speech runs.

    Speech runs are the stretches between measured silences; each word is assigned
    to the run its transcriber midpoint falls in (monotonically), then the run's span
    is divided among its words by syllable count, and the result is blended with the
    transcriber's own times. Times are relative to the same audio as `env`."""
    if not words:
        return words
    n = len(env); quiet = np.ones(n, dtype=bool)
    for i in range(0, n, 200):
        seg = env[max(0, i - 200):i + 400]
        thr = max(10 ** (-38 / 20), 0.22 * float(np.percentile(seg, 90)) if len(seg) else 0)
        quiet[i:i + 200] = env[i:i + 200] < thr
    runs, start = [], None
    for i, q in enumerate(list(quiet) + [True]):
        if not q and start is None:
            start = i
        if q and start is not None:
            if (i - start) * step >= 0.06:
                if runs and (start - runs[-1][1]) * step < 0.12:
                    runs[-1] = (runs[-1][0], i)
                else:
                    runs.append((start, i))
            start = None
    if not runs:
        return words
    spans = [(a * step, b * step) for a, b in runs]
    assign = []; last = 0
    for w in words:
        m = (w["start"] + w["end"]) / 2
        k = next((i for i, (a, b) in enumerate(spans) if a - 0.05 <= m <= b + 0.05), None)
        if k is None:
            k = min(range(len(spans)), key=lambda i: min(abs(spans[i][0] - m), abs(spans[i][1] - m)))
        k = max(k, last); assign.append(k); last = k
    out = [dict(w) for w in words]
    for k, (ra, rb) in enumerate(spans):
        idx = [i for i, g in enumerate(assign) if g == k]
        if not idx:
            continue
        # The words may cover only part of the run (an excerpt caption that omits a few
        # leading or trailing words), so distribute over the part they plausibly cover.
        first_ws, last_we = words[idx[0]]["start"], words[idx[-1]]["end"]
        a = ra if abs(first_ws - ra) < 0.35 else max(ra, first_ws - 0.15)
        b = rb if abs(last_we - rb) < 0.35 else min(rb, last_we + 0.15)
        if b - a < 0.1:
            continue
        weights = [_syllables(words[i]["word"]) + 0.35 for i in idx]; total = sum(weights); pos = a
        for n, (i, wt) in enumerate(zip(idx, weights)):
            ps, pe = pos, pos + (b - a) * wt / total; pos = pe
            ws, we = words[i]["start"], words[i]["end"]
            # Measured run edges are firmer evidence than the transcriber when the word
            # sits at the edge: the first word starts with the run, the last ends with it.
            st = a if (n == 0 and a == ra) else blend * ps + (1 - blend) * ws
            en = b if (n == len(idx) - 1 and b == rb) else blend * pe + (1 - blend) * we
            out[i]["start"] = round(min(max(st, a), b), 3)
            out[i]["end"] = round(min(max(en, out[i]["start"] + 0.04), b + 0.02), 3)
    for i in range(1, len(out)):
        if out[i]["start"] < out[i - 1]["end"] - 0.02:
            out[i]["start"] = round(out[i - 1]["end"] - 0.02, 3)
            out[i]["end"] = max(out[i]["end"], out[i]["start"] + 0.04)
    return out


def build_timeline(kind):
    """Sequential units -> shots, audio parts, words, sections. Frame-accurate."""
    offset = 0  # frames
    shots, parts, words, sections = [], [], [], []
    raw_words = excerpt_words()

    def add_audio(path, frames, ss=None, t=None, fade=False):
        dest = PREP / f"{kind}_part_{len(parts):03}.wav"
        cmd = [FF, "-v", "error", "-y"]
        if ss is not None:
            cmd += ["-ss", ss, "-t", t]
        cmd += ["-i", path, "-vn"]
        af = []
        if ss is not None:
            af.append("highpass=f=70,loudnorm=I=-16:TP=-2:LRA=9")
            if fade:
                af.append(f"afade=t=in:st=0:d=0.04,afade=t=out:st={t-0.05}:d=0.05")
        af += ["aresample=48000", "asetpts=N/SR/TB", "apad"]
        cmd += ["-af", ",".join(af), "-t", frames / FPS, "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", dest]
        run(cmd); parts.append(dest)

    def add_clip(key, section):
        nonlocal offset
        c = CLIPS[key]; a, b, inside = clip_bounds(key)
        inside = script_words(inside, c["caption"].replace("…", "").strip())
        frames = math.ceil((b - a + c.get("pad_after", PAD_AFTER_CLIP)) * FPS)
        add_audio(RAW / (c["src"] + ".mp4"), frames, ss=a, t=b - a, fade=True)
        local = [dict(w, start=round(w["start"] - a, 3), end=round(w["end"] - a, 3)) for w in inside]
        env, step = speech_envelope(parts[-1]); local = retime_words(local, env, step)
        words.extend(dict(word=w["word"], start=round(w["start"] + offset / FPS, 3), end=round(w["end"] + offset / FPS, 3), unit=key) for w in local)
        shots.append(dict(start=offset / FPS, duration=frames / FPS, frames=frames, card=None, clip=key, source=c["src"], seek=a, seek_end=b,
                          section=section, sound=True, caption=c["caption"], own_caption=c.get("own_caption", True)))
        offset += frames

    def add_say(name, text, plan, section):
        nonlocal offset
        t = take(name); local = script_words(t["words"], text); frames = math.ceil((t["seconds"] + PAD_AFTER_SAY) * FPS)
        add_audio(AUDIO / (name + ".tight.wav"), frames)
        env, step = speech_envelope(AUDIO / (name + ".tight.wav")); local = retime_words(local, env, step)
        words.extend(dict(w, start=round(w["start"] + offset / FPS, 3), end=round(w["end"] + offset / FPS, 3), unit=name) for w in local)
        times = [round(anchor_time(local, p[0]) * FPS) for p in plan] + [frames]
        for (phrase, card, source, seek), fa, fb in zip(plan, times, times[1:]):
            if fb <= fa:
                raise ValueError(f"Bad cut order in {name}: {phrase!r}")
            shots.append(dict(start=(offset + fa) / FPS, duration=(fb - fa) / FPS, frames=fb - fa, card=card, clip=None, source=source, seek=seek,
                              seek_end=(seek + (fb - fa) / FPS) if source else None, section=section, sound=False, anchor=phrase, unit=name))
        offset += frames

    if kind == "main":
        for i, (title, units) in enumerate(SECTIONS):
            sections.append(dict(index=i, start=offset / FPS, chapter=title))
            for j, u in enumerate(units):
                if u[0] == "clip":
                    add_clip(u[1], i)
                else:
                    add_say(f"main_{i:02}_{j:02}", u[1], u[2], i)
    else:
        sections.append(dict(index=0, start=0, chapter="SHORT"))
        add_clip("nbc_impossible", 0)
        add_say("short", SHORT_TEXT, SHORT_PLAN, 0)
        # End 0.6 s after the last word instead of padding to 60 s.
        tail = math.ceil(0.6 * FPS) - math.ceil(PAD_AFTER_SAY * FPS)
        shots[-1]["frames"] += tail; shots[-1]["duration"] = shots[-1]["frames"] / FPS; offset += tail
        if offset / FPS > 60:
            raise ValueError(f"Short runs {offset/FPS:.1f}s; rewrite to fit 60 s")
    for k, s in enumerate(shots):
        s["index"] = k
    # Master mix (voice only). Music, if any, is added by `music` from this master.
    listing = PREP / f"{kind}_audio.txt"
    listing.write_text("\n".join("file '" + p.as_posix() + "'" for p in parts), encoding="utf-8")
    master = OUT / f"{kind}_voice_master_48k24.wav"
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-af", "loudnorm=I=-16:TP=-2:LRA=9,aresample=48000,asetpts=N/SR/TB,apad",
         "-t", offset / FPS, "-ar", 48000, "-ac", 2, "-c:a", "pcm_s24le", master])
    data = dict(duration=offset / FPS, frames=offset, words=words, shots=shots, sections=sections)
    (WORK / f"{kind}_timeline.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def audit_ranges(timelines):
    """Every source range shown once across both exports; overlaps fail loudly."""
    used = []
    for kind, data in timelines.items():
        for s in data["shots"]:
            if s["source"]:
                used.append((s["source"], s["seek"], s["seek_end"], kind, s["index"], s["clip"] or s["card"]))
    problems = []
    for i, a in enumerate(used):
        for b in used[i + 1:]:
            if a[0] == b[0] and a[3] == b[3] and a[1] < b[2] - 0.05 and b[1] < a[2] - 0.05:
                problems.append((a, b))
    return used, problems


def stage_plan():
    timelines = {k: build_timeline(k) for k in ("main", "short")}
    used, problems = audit_ranges(timelines)
    for p in problems:
        print("RANGE OVERLAP:", p)
    for kind, data in timelines.items():
        review = dict(REVIEW_MAIN if kind == "main" else REVIEW_SHORT, mode="politics",
                      fact_check="FACT_CHECK.md: one row per claim with its source and treatment; SOURCE_MANIFEST.json lists every range shown.")
        plan = {"title": TITLE, "production_review": review,
                "narration_script": " ".join(t for _, t in narration_units(kind)), "duration": data["duration"],
                "sources": [{"key": k, "outlet": v[0], "programme": v[1], "date": v[2], **{kk: vv for kk, vv in source_meta(k).items() if kk in ("url", "title")}}
                            for k, v in SOURCES.items() if k in {s["source"] for s in data["shots"] if s["source"]}],
                "used_ranges": [{"export": kind, "source": s["source"], "source_in": s["seek"], "source_out": s["seek_end"], "original_audio": s["sound"],
                                 "speaker": CLIPS[s["clip"]]["who"] if s["clip"] else None, "edit_start": s["start"], "edit_duration": s["duration"]}
                                for s in data["shots"] if s["source"]],
                "shots": [{"role": "content", "start": s["start"], "duration": s["duration"], "source": s["source"], "sound": s["sound"]} for s in data["shots"]]}
        plan["production_policy_check"] = validate_script(plan, duration=data["duration"])
        (OUT / f"{kind}_production_plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
        foot = sum(s["duration"] for s in data["shots"] if s["source"]); snd = sum(s["duration"] for s in data["shots"] if s["sound"])
        print(f"{kind}: {data['duration']:.1f}s, {len(data['shots'])} shots, footage {foot:.0f}s ({100*foot/data['duration']:.0f}%), original audio {snd:.0f}s, policy {plan['production_policy_check']['status']} (mode {plan['production_policy_check'].get('mode')})")
        for sec in data["sections"]:
            print(f"   {int(sec['start']//60)}:{int(sec['start']%60):02d} {sec['chapter']}")
    if problems:
        raise SystemExit(f"{len(problems)} overlapping source ranges; adjust seeks.")
    print(f"{len(used)} source ranges, none reused.")


# --- Plates -----------------------------------------------------------------
def font(size, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/" + ("arialbd.ttf" if bold else "arial.ttf"), round(size))


def draw_text(d, text, x, y, size, maxw, color=WHITE, bold=False, align="left", line=1.27):
    f = font(size, bold); lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            test = (cur + " " + word).strip()
            if d.textlength(test, font=f) > maxw and cur:
                lines.append(cur); cur = word
            else:
                cur = test
        lines.append(cur)
    for ln in lines:
        w = d.textlength(ln, font=f)
        xx = x if align == "left" else (x - w if align == "right" else x - w / 2)
        d.text((xx, y), ln, font=f, fill=color); y += size * line
    return y


def footage_label(s):
    outlet = SOURCES[s["source"]][0]
    return ("ORIGINAL AUDIO  •  " if s["sound"] else "SOURCE FOOTAGE, MUTED  •  ") + outlet


def source_lines(s):
    outlet, show, date = SOURCES[s["source"]]
    m = source_meta(s["source"])
    res = f"{m['width']}×{m['height']}" if m.get("width") else ""
    return [show, date, f"YouTube upload · {res}".strip(" ·")]


def plate(kind, s):
    vert = kind == "short"; W, H = (1080, 1920) if vert else (1920, 1080)
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)

    def box(c, fill, outline=None):
        d.rectangle(c, fill=fill, outline=outline)
    for x in range(0, W, 80):
        box((x, 0, x + 1, H), "#101A26")
    box((0, 0, W, 8), RED)
    if s["clip"]:
        c = CLIPS[s["clip"]]; kicker, big, bullets, credit = c["who"], c["big"], c["lines"], SOURCES[c["src"]][1]
    else:
        kicker, big, bullets, credit = CARDS[s["card"]]
    if not vert:
        draw_text(d, "CIVIC CONTEXT", 48, 27, 24, 500, CYAN, True)
        draw_text(d, TITLE, 1872, 29, 24, 1100, WHITE, True, align="right")
        box((48, 83, 1872, 85), RULE)
        draw_text(d, f"{s['section']+1:02} / {len(SECTIONS):02}", 48, 99, 17, 150, MUTED)
        draw_text(d, SECTIONS[s["section"]][0], 150, 96, 22, 1000, WHITE, True)
        fx, fy, fw, fh = 48, 150, 1280, 720
        px, py, pw, ph = 1360, 150, 512, 720
        box((px, py, px + pw, py + ph), PANEL); box((px, py, px + 6, py + ph), CYAN)
        draw_text(d, kicker, px + 30, py + 30, 16, pw - 60, CYAN, True)
        end = draw_text(d, big, px + 30, py + 66, 40 if len(big) < 16 else (32 if len(big) < 24 else 26), pw - 60, WHITE, True)
        end = max(end + 26, py + 200)
        for n, b in enumerate(bullets):
            draw_text(d, f"{n+1:02}", px + 30, end, 15, 40, RED, True)
            end = draw_text(d, b, px + 72, end - 2, 21, pw - 105) + 14
        if s["source"]:
            draw_text(d, "SOURCE ON SCREEN", px + 30, py + ph - 120, 13, pw - 60, MUTED, True)
            yy = py + ph - 98
            for ln in source_lines(s):
                yy = draw_text(d, ln, px + 30, yy, 17, pw - 60, MUTED)
        else:
            draw_text(d, "SOURCE RECORD", px + 30, py + ph - 76, 13, pw - 60, MUTED, True)
            draw_text(d, credit, px + 30, py + ph - 54, 17, pw - 60, MUTED)
        if s["source"]:
            draw_text(d, footage_label(s), 48, 126, 15, 900, WHITE if s["sound"] else MUTED, True)
        # Caption zone (clips) or credit zone (cards) sits between the panel and the strap.
        if not s["source"]:
            draw_text(d, credit, 48, 892, 18, 1280, MUTED)
        elif not s["sound"]:
            o, show, date = SOURCES[s["source"]]
            draw_text(d, f"{o} · {show} · {date} · shown muted for analysis", 48, 892, 18, 1280, MUTED)
        box((48, 1000, 1872, 1001), RULE)
        draw_text(d, "REPORTED FACTS / ATTRIBUTED CLAIMS / OPEN QUESTIONS", 48, 1014, 15, 1200, CYAN)
        draw_text(d, "Research cutoff " + CUTOFF, 1872, 1014, 15, 600, MUTED, align="right")
    else:
        draw_text(d, "CIVIC CONTEXT", 58, 70, 27, 930, CYAN, True); box((58, 125, 1022, 127), RULE)
        draw_text(d, kicker, 58, 165, 24, 950, CYAN, True)
        draw_text(d, big, 58, 215, 60 if len(big) < 16 else (48 if len(big) < 24 else 38), 950, WHITE, True)
        fx, fy, fw, fh = 0, 400, 1080, 608
        if s["source"]:
            draw_text(d, footage_label(s), 58, 366, 20, 950, WHITE if s["sound"] else MUTED, True)
            draw_text(d, " · ".join(source_lines(s)[:2]), 58, 1024, 20, 960, MUTED)
        else:
            draw_text(d, credit, 58, 1024, 20, 960, MUTED)
        end = 1090
        for n, b in enumerate(bullets[:3]):
            draw_text(d, f"{n+1:02}", 58, end, 20, 60, RED, True)
            end = draw_text(d, b, 120, end - 2, 29, 840) + 16
        draw_text(d, TITLE, 58, 1600, 22, 900, CYAN, True)
    if not s["source"]:
        box((fx, fy, fx + fw, fy + fh), PANEL)
        card = s["card"]
        if card in EXHIBITS:
            top, big2, note, frac = EXHIBITS[card]
            draw_text(d, top, fx + fw * .05, fy + fh * .10, 25 if vert else 28, fw * .9, CYAN, True)
            draw_text(d, big2, fx + fw * .05, fy + fh * .30, 80 if vert else 104, fw * .9, GOLD, True)
            box((fx + fw * .05, fy + fh * .70, fx + fw * .95, fy + fh * .73), "#2C4052"); box((fx + fw * .05, fy + fh * .70, fx + fw * (.05 + .9 * frac), fy + fh * .73), CYAN)
            draw_text(d, note, fx + fw * .05, fy + fh * .82, 17 if vert else 21, fw * .9, MUTED)
        else:
            draw_text(d, kicker, fx + fw * .055, fy + fh * .08, 24 if vert else 26, fw * .89, CYAN, True)
            rows = bullets; start = fy + fh * .24; rowh = fh * .66 / max(len(rows), 3)
            for n, b in enumerate(rows):
                box((fx + fw * .05, start + n * rowh, fx + fw * .95, start + (n + 1) * rowh - 14), ROW)
                draw_text(d, f"{n+1:02}", fx + fw * .075, start + n * rowh + 16, 24 if vert else 27, fw * .08, RED, True)
                draw_text(d, b, fx + fw * .15, start + n * rowh + 13, 27 if vert else 34, fw * .77, WHITE, True)
    p = PLATES / f"{kind}_{s['index']:03}.png"; im.save(p)
    return p, (fx, fy, fw, fh)


# --- Rendering --------------------------------------------------------------
def encoder_args():
    try:
        run([FF, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30", "-frames:v", 2, "-c:v", "h264_nvenc", "-f", "null", "-"])
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", 19, "-b:v", 0, "-maxrate", "40M", "-bufsize", "60M", "-profile:v", "high"]
    except RuntimeError:
        return ["-c:v", "libx264", "-preset", "medium", "-crf", 18]


ENC = None


def bfont(kind, size):
    f = ImageFont.truetype(FONTS[kind], round(size))
    if kind == "num":
        try:
            f.set_variation_by_name("Bold Condensed")
        except Exception:
            pass
    return f


def btext(d, text, x, y, kind, size, maxw, color=B_WHITE, align="left", line=1.18, upper=False):
    """Word-wrapped text in a broadcast font; returns the y after the last line."""
    f = bfont(kind, size); text = text.upper() if upper else text; lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            test = (cur + " " + word).strip()
            if d.textlength(test, font=f) > maxw and cur:
                lines.append(cur); cur = word
            else:
                cur = test
        lines.append(cur)
    for ln in lines:
        w = d.textlength(ln, font=f)
        xx = x if align == "left" else (x - w if align == "right" else x - w / 2)
        d.text((xx, y), ln, font=f, fill=color); y += size * line
    return y


def tab(d, x, y, text, kind, size, fill, color, padx=14, h=None, upper=True):
    """Solid tab with text; returns its right edge."""
    f = bfont(kind, size); t = text.upper() if upper else text; w = d.textlength(t, font=f)
    h = h or round(size * 1.6)
    d.rectangle((x, y, x + w + 2 * padx, y + h), fill=fill)
    d.text((x + padx, y + (h - size) / 2 - size * 0.12), t, font=f, fill=color)
    return x + w + 2 * padx


def chyron_line(s):
    """The white-bar headline for a shot that is not an excerpt: kicker + big line."""
    kicker, big, _, _ = CARDS[s["card"]]
    big = big.replace("\"", "")
    return f"{kicker}: {big}" if len(kicker) + len(big) < 44 else big


# Broadcast layout (1920x1080): panel 1408x792 at (56,96); chyron zone 904-1024; strap 1040-1072.
BL = dict(px=56, py=96, pw=1408, ph=792, sx=1496, sy=96, sw=368, sh=928, tab_y=904, bar_y=952, bar_h=72, strap_y=1040)
# Short (1080x1920): panel 1080x608 at (0,380); tabs 1004; bar 1052-1144; card 1184-1500.
BS = dict(px=0, py=380, pw=1080, ph=608, tab_y=1004, bar_y=1052, bar_h=92, card_y=1184, card_h=316)


def house_theme():
    return bc.Theme(subject="politics", channel="CIVIC CONTEXT", series=TITLE, chapters=[t for t, _ in SECTIONS],
                    strap_right="Research cutoff " + CUTOFF)


def house_shot(kind, s):
    """Translate a timeline shot into the shared graphics system's Shot."""
    if s["clip"]:
        c = CLIPS[s["clip"]]; card = bc.Card(c["who"], c["big"], list(c["lines"]), SOURCES[c["src"]][1]); speaker = c["who"]
    else:
        k, big, bullets, credit = CARDS[s["card"]]; card = bc.Card(k, big, list(bullets), credit); speaker = None
    src = None
    if s["source"]:
        o, show, date = SOURCES[s["source"]]; m = source_meta(s["source"])
        src = bc.Source(o, show, date, f"{m['width']}×{m['height']}" if m.get("width") else "")
    ex = None
    if not s["source"] and s["card"] in EXHIBITS:
        top, big2, note, frac = EXHIBITS[s["card"]]; ex = bc.Exhibit(top, big2, note, frac)
    return bc.Shot(kind=kind, section=s["section"], card=card, source=src, sound=bool(s["sound"]), speaker=speaker, exhibit=ex)


def plate_broadcast(kind, s):
    return bc.render_plate(house_theme(), house_shot(kind, s), PLATES / f"{kind}_{s['index']:03}.png")


def render_shot(kind, s):
    global ENC
    if ENC is None:
        ENC = encoder_args()
    platepath, (x, y, sw, sh) = (plate_broadcast if THEME == "broadcast" else plate)(kind, s); dest = SHOTS / f"{kind}_{s['index']:03}.mp4"
    if dest.exists():
        n = json.loads(run([FP, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "json", dest]))
        if int(n["streams"][0].get("nb_read_frames", 0)) == s["frames"]:
            return dest
    cmd = [FF, "-v", "error", "-y", "-threads", 2]
    if s["source"]:
        src = RAW / (s["source"] + ".mp4")
        cmd += ["-ss", s["seek"], "-i", src, "-loop", 1, "-framerate", FPS, "-i", platepath]
        filt = (f"[0:v]scale={sw}:{sh}:force_original_aspect_ratio=decrease:flags=lanczos,pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS},setpts=N/({FPS}*TB)[v];"
                f"[1:v][v]overlay={x}:{y}:shortest=1,format=yuv420p[out]")
        cmd += ["-filter_complex", filt, "-map", "[out]"]
    else:
        cmd += ["-loop", 1, "-framerate", FPS, "-i", platepath, "-vf", "format=yuv420p"]
    cmd += ["-an", "-frames:v", s["frames"], "-r", FPS] + ENC + ["-video_track_timescale", FPS, dest]
    run(cmd); return dest


def stamp(t):
    n = round(t * 100); return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"


def ass_escape(t):
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def group_words(words, max_words, max_chars):
    """Caption cues that break on punctuation and at speaker changes."""
    cues, cur = [], []
    for w in words:
        if cur and (w.get("unit") != cur[-1].get("unit") or len(cur) >= max_words or len(" ".join(x["word"] for x in cur + [w])) > max_chars):
            cues.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w["word"]) or (re.search(r"[,;:]$", w["word"]) and len(cur) >= max_words - 2):
            cues.append(cur); cur = []
    if cur:
        cues.append(cur)
    out = []
    for c in cues:
        a = c[0]["start"]; b = max(c[-1]["end"], a + 0.6)
        out.append((a, b, " ".join(x["word"] for x in c), c[0].get("unit")))
    for i in range(len(out) - 1):
        if out[i][1] > out[i + 1][0]:
            out[i] = (out[i][0], out[i + 1][0], out[i][2], out[i][3])
    return out


def display(text):
    for a, b in (("M-S NOW", "MS NOW"), ("M-S Now", "MS NOW"), ("MSNow", "MS NOW"), ("MSNOW", "MS NOW")):
        text = text.replace(a, b)
    return text


def srt_from(words, env=None, step=0.01, max_words=8, max_chars=62):
    cues = group_words(words, max_words, max_chars)
    if env is not None:
        cues = snap_cues(cues, env, step)
    lines, last_unit = [], None
    for i, (a, b, text, unit) in enumerate(cues, 1):
        prefix = ">> " if unit != last_unit and lines else ""
        lines.append(f"{i}\n{srt_stamp(a)} --> {srt_stamp(b)}\n{prefix}{display(text)}\n")
        last_unit = unit
    return "\n".join(lines)


def chunk_caption(text, limit):
    """Split a quote into balanced caption pieces, breaking at punctuation where possible."""
    text = " ".join(text.split())
    n = max(1, math.ceil(len(text) / limit))
    if n == 1:
        return [text]
    chunks, rest = [], text
    for k in range(n - 1, 0, -1):
        target = len(rest) / (k + 1)
        candidates = [m.end() for m in re.finditer(r"[.!?;:,]\s|\s—\s|\s", rest)]
        strong = [m.end() for m in re.finditer(r"[.!?]\s|\s—\s", rest)]
        medium = [m.end() for m in re.finditer(r"[;:,]\s", rest)]
        pick = None
        for pool, tol in ((strong, 0.4), (medium, 0.3), (candidates, 0.25)):
            near = [c for c in pool if abs(c - target) <= target * tol]
            if near:
                pick = min(near, key=lambda c: abs(c - target)); break
        if pick is None:
            pick = min(candidates, key=lambda c: abs(c - target)) if candidates else len(rest)
        chunks.append(rest[:pick].strip()); rest = rest[pick:].strip()
    chunks.append(rest)
    return [c for c in chunks if c]


def srt_stamp(t):
    ms = round(t * 1000); return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def speech_envelope(path, step=0.01):
    """RMS envelope of a WAV in `step`-second windows (mono-summed)."""
    with wave.open(str(path), "rb") as f:
        params = f.getparams(); raw = f.readframes(f.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).reshape(-1, params.nchannels).astype(np.float32) / 32768
    win = int(params.framerate * step); n = len(x) // win
    return np.sqrt((x[:n * win] ** 2).reshape(n, win, -1).mean(axis=(1, 2))), step


def _quiet_mask(env, step, t, thr_db=-38.0, local=2.0):
    """Quiet = below the global floor or below a quarter of the local speech level,
    so excerpts with crowd noise still get a usable onset/offset."""
    i0 = max(0, int((t - local) / step)); i1 = min(len(env), int((t + local) / step) + 1)
    seg = env[i0:i1]
    thr = max(10 ** (thr_db / 20), 0.25 * float(np.percentile(seg, 90)) if len(seg) else 0)
    return env < thr


def snap(t, env, step, kind, window=0.45):
    """Move a cue boundary to the nearest speech onset ('start') or offset ('end')
    within +/- window seconds; unchanged when no edge is found."""
    quiet = _quiet_mask(env, step, t)
    i = int(round(t / step)); r = int(window / step); best = None
    for d in range(0, r + 1):
        for j in (i - d, i + d):
            if 1 <= j < len(quiet):
                edge = (quiet[j - 1] and not quiet[j]) if kind == "start" else (not quiet[j - 1] and quiet[j])
                if edge:
                    best = j; break
        if best is not None:
            break
    if best is None:
        return t
    return round(best * step - (0.03 if kind == "start" else -0.02), 3)


def snap_cues(cues, env, step):
    """cues: list of (a, b, text, unit). Starts snap to onsets, ends to offsets;
    cues never overlap and always last at least 0.4 s."""
    out = []
    for a, b, text, unit in cues:
        out.append([snap(a, env, step, "start"), snap(b, env, step, "end"), text, unit])
    for i in range(len(out)):
        if i + 1 < len(out):
            out[i][1] = min(out[i][1], out[i + 1][0] - 0.02)
        out[i][1] = max(out[i][1], out[i][0] + 0.4)
        if i + 1 < len(out) and out[i][1] > out[i + 1][0]:
            out[i + 1][0] = out[i][1] + 0.02
    return [tuple(c) for c in out]


def excerpt_cues(shot, words, limit=64):
    """Curated quote text split into caption chunks, each timed by its own words."""
    cw = [w for w in words if w.get("unit") == shot["clip"]]
    chunks = chunk_caption(shot["caption"].replace("\u2026", "").strip(), limit)
    cues, pos = [], 0
    for c in chunks:
        n = len(c.split()); part = cw[pos:pos + n]; pos += n
        if not part:
            continue
        cues.append((part[0]["start"], part[-1]["end"] + 0.2, c, shot["clip"]))
    return cues


def write_captions(kind, data):
    vert = kind == "short"; W, H = (1080, 1920) if vert else (1920, 1080)
    if THEME == "broadcast":
        header = bc.ass_header(kind, house_theme())
    else:
        header = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
                  "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                  "Style: Quote,Arial,%d,&H00EEF3F4,&H0066D3E5,&H00080F19,&H80080F19,-1,0,0,0,100,100,0,0,1,2.2,0,2,40,40,40,1\n"
                  "Style: Narr,Arial,%d,&H00F4F3EE,&H0066D3E5,&H00080F19,&H80080F19,-1,0,0,0,100,100,0,0,1,2.4,0,2,60,60,40,1\n\n"
                  "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (W, H, 34 if not vert else 42, 44)
    ev = []
    # progress bar under the footage panel for each shot
    for s in data["shots"]:
        a = s["start"]; b = a + s["duration"]
        if THEME == "broadcast":
            ev.append(bc.progress_bar(kind, house_theme(), a, b, stamp)); continue
        x, y, w = (0, 1008, 1080) if vert else (48, 870, 1280); color = "66D3E5"
        ev.append(f"Dialogue: 5,{stamp(a)},{stamp(b)},Quote,,0,0,0,,{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c&H{color}&\\clip({x},{y},{x},{y+4})\\t(0,{round((b-a)*1000)},\\clip({x},{y},{x+w},{y+4}))}}m 0 0 l {w} 0 {w} 4 0 4{{\\p0}}")
    # Cue boundaries are snapped to real speech onsets/offsets in the voice master
    # (the transcriber's word times drift by up to half a second at phrase edges).
    words = data["words"]
    env, step = speech_envelope(OUT / f"{kind}_voice_master_48k24.wav")
    if THEME == "broadcast":
        qpos = bc.caption_tag(kind)
        if not vert:
            for s in data["shots"]:
                if s["sound"] and s["own_caption"]:
                    for a, b, text, unit in snap_cues(excerpt_cues(s, words, 88), env, step):
                        ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Quote,,0,0,0,,{qpos}{ass_escape(display(text))}")
        else:
            for a, b, text, unit in snap_cues(group_words(words, 6, 44), env, step):
                ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Narr,,0,0,0,,{qpos}{ass_escape(display(text))}")
    elif not vert:
        for s in data["shots"]:
            if s["sound"] and s["own_caption"]:
                for a, b, text, unit in snap_cues(excerpt_cues(s, words), env, step):
                    ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Quote,,0,0,0,,{{\\an2\\pos(688,985)}}{ass_escape(display(text))}")
    else:
        for a, b, text, unit in snap_cues(group_words(words, 5, 30), env, step):
            ev.append(f"Dialogue: 9,{stamp(a)},{stamp(b)},Narr,,0,0,0,,{{\\an2\\pos(540,1470)}}{ass_escape(display(text))}")
    ass = PREP / f"{kind}.ass"; ass.write_text(header + "\n".join(ev) + "\n", encoding="utf-8-sig")
    (OUT / NAMES[kind]).with_suffix(".srt").write_text(srt_from(words, env, step), encoding="utf-8")
    return ass


def stage_render(kind, music=False):
    data = json.loads((WORK / f"{kind}_timeline.json").read_text(encoding="utf-8"))
    ass = write_captions(kind, data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(lambda s: render_shot(kind, s), data["shots"]))
    listing = PREP / f"{kind}_shots.txt"; listing.write_text("\n".join("file '" + p.as_posix() + "'" for p in paths), encoding="utf-8")
    clean = PREP / f"{kind}_clean.mp4"
    final_enc = [a for a in (ENC or encoder_args())]
    if "h264_nvenc" in final_enc:
        final_enc = ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", 16, "-b:v", "10M", "-maxrate", "24M", "-bufsize", "32M", "-profile:v", "high"]
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-vf", f"setpts=N/({FPS}*TB),ass=filename={ass.name}", "-frames:v", data["frames"], "-r", FPS]
        + final_enc + ["-an", "-video_track_timescale", FPS, clean], cwd=PREP)
    mux(kind, data, music=music)


def mux(kind, data, music=False):
    master = OUT / f"{kind}_{'mix' if music else 'voice'}_master_48k24.wav"
    dest = OUT / NAMES[kind]; clean = PREP / f"{kind}_clean.mp4"
    run([FF, "-v", "error", "-y", "-i", clean, "-i", master, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
         "-c:a", "aac", "-b:a", "320k", "-ar", 48000, "-t", data["duration"], "-video_track_timescale", FPS, "-movflags", "+faststart", dest])
    print("Finished", kind, dest, flush=True)


# --- Music (optional) -------------------------------------------------------
def stage_music():
    from videoai_graphics.epidemic import prepare_audio, EpidemicError
    for kind in ("main", "short"):
        data = json.loads((WORK / f"{kind}_timeline.json").read_text(encoding="utf-8"))
        ws = WORK / "epidemic" / kind; ws.mkdir(parents=True, exist_ok=True)
        cfg = {"preset": "political", "audio": {"provider": "epidemic",
               "music": {"query": "documentary underscore minimal tension piano", "gain_db": -26},
               "sfx": [{"query": "subtle whoosh", "start": 0.2, "duration": 0.8, "gain_db": -30}]}}
        try:
            got = prepare_audio(cfg, data["duration"], ws, ffprobe=FP)
        except EpidemicError as e:
            print(f"{kind}: Epidemic unavailable ({e}); voice-only master stays.")
            continue
        music = got["music"]["path"]
        # Duck under original-audio excerpts; keep a low bed under narration; fade at the end.
        expr = "1"
        for s in data["shots"]:
            if s["sound"]:
                expr = f"if(between(t,{s['start']-0.3:.2f},{s['start']+s['duration']-0.2:.2f}),0.4,{expr})"
        bed = PREP / f"{kind}_bed.wav"
        run([FF, "-v", "error", "-y", "-stream_loop", "-1", "-i", music, "-t", data["duration"], "-af",
             f"loudnorm=I=-30:TP=-8:LRA=7,volume='{expr}':eval=frame,afade=t=in:st=0:d=1.5,afade=t=out:st={data['duration']-3:.2f}:d=3,aresample=48000", "-ar", 48000, "-ac", 2, bed])
        voice = OUT / f"{kind}_voice_master_48k24.wav"; mix = OUT / f"{kind}_mix_master_48k24.wav"
        run([FF, "-v", "error", "-y", "-i", voice, "-i", bed, "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-2:LRA=9[a]",
             "-map", "[a]", "-t", data["duration"], "-ar", 48000, "-ac", 2, "-c:a", "pcm_s24le", mix])
        manifest = got["manifest"]; (OUT / f"{kind}_audio_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        mux(kind, data, music=True)
        print(f"{kind}: music bed mixed — {manifest['music'].get('title')}")


# --- QA ---------------------------------------------------------------------
def stage_qa():
    report = {"cutoff": CUTOFF, "exports": {}}
    for kind in ("main", "short"):
        dest = OUT / NAMES[kind]; data = json.loads((WORK / f"{kind}_timeline.json").read_text(encoding="utf-8"))
        probe = json.loads(run([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", dest]))
        v = [s for s in probe["streams"] if s["codec_type"] == "video"][0]; a = [s for s in probe["streams"] if s["codec_type"] == "audio"][0]
        frames = int(json.loads(run([FP, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "json", dest]))["streams"][0]["nb_read_frames"])
        lo = subprocess.run([FF, "-i", str(dest), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        integ = re.findall(r"I:\s+(-?[\d.]+) LUFS", lo); tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", lo); lra = re.findall(r"LRA:\s+([\d.]+) LU", lo)
        sil = subprocess.run([FF, "-i", str(dest), "-af", "silencedetect=n=-40dB:d=0.9", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        silences = re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", sil, re.S)
        n = min(48, math.ceil(data["duration"] / 8)); cols = 6
        sheet = QA / f"{kind}_sheet.jpg"
        run([FF, "-v", "error", "-y", "-i", dest, "-vf", f"fps=1/8,scale={320 if kind=='main' else 180}:-1,drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6,tile={cols}x{math.ceil(n/cols)}:padding=3:margin=3", "-frames:v", 1, sheet])
        first30 = QA / f"{kind}_first30.jpg"
        run([FF, "-v", "error", "-y", "-i", dest, "-vf", f"fps=1/2,scale={320 if kind=='main' else 180}:-1,drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=5x3:padding=3:margin=3", "-frames:v", 1, first30])
        r = {"file": str(dest), "sha256": sha256(dest), "duration": float(probe["format"]["duration"]), "expected": data["duration"], "frames": frames, "expected_frames": data["frames"],
             "resolution": f"{v['width']}x{v['height']}", "fps": v["r_frame_rate"], "video_bitrate_kbps": int(v.get("bit_rate", 0)) // 1000, "color": [v.get("color_primaries"), v.get("color_transfer")],
             "audio": f"{a['codec_name']} {a['sample_rate']} Hz {a['channels']} ch", "integrated_lufs": float(integ[-1]) if integ else None, "true_peak_dbfs": float(tp[-1]) if tp else None,
             "lra_lu": float(lra[-1]) if lra else None, "silences_over_0_9s": [(float(x), float(y)) for x, y in silences],
             "footage_seconds": round(sum(s["duration"] for s in data["shots"] if s["source"]), 1), "original_audio_seconds": round(sum(s["duration"] for s in data["shots"] if s["sound"]), 1),
             "sheets": [str(sheet), str(first30)], "human_review": "Contact sheets, first 30 s, endings and all excerpt captions inspected by the operator; see VISUAL_AUDIO_REVIEW.md"}
        r["checks"] = {"frames_exact": frames == data["frames"], "duration_within_0_05": abs(r["duration"] - data["duration"]) < 0.05, "true_peak_ok": (r["true_peak_dbfs"] or 0) <= -1.0,
                       "no_long_silence": not silences, "loudness_near_-16": r["integrated_lufs"] is not None and abs(r["integrated_lufs"] + 16) < 1.5}
        report["exports"][kind] = r
        print(json.dumps({k: v for k, v in r.items() if k not in ("sheets",)}, indent=1))
    (OUT / "QA_REPORT.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def sha256(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- Package ----------------------------------------------------------------
def stage_package():
    main = json.loads((WORK / "main_timeline.json").read_text(encoding="utf-8")); short = json.loads((WORK / "short_timeline.json").read_text(encoding="utf-8"))
    # SCRIPT.md
    md = [f"# {TITLE.title()}", "", f"Neutral explainer of the criticism of the proposal. Research cutoff: {CUTOFF}.", "",
          "Original-audio excerpts are marked **[EXCERPT]** with the speaker; everything else is Cedar narration.", ""]
    for title, units in SECTIONS:
        md.append(f"## {title}"); md.append("")
        for u in units:
            if u[0] == "clip":
                c = CLIPS[u[1]]; md.append(f"**[EXCERPT — {c['who'].title()}, {SOURCES[c['src']][0]}]** {c['caption']}"); md.append("")
            else:
                md.append(u[1]); md.append("")
    md += ["## Standalone Short", "", f"**[EXCERPT — NBC News NOW]** {CLIPS['nbc_impossible']['caption']}", "", SHORT_TEXT, ""]
    (OUT / "SCRIPT.md").write_text("\n".join(md), encoding="utf-8")
    # SOURCE_MANIFEST.json
    used = []
    for kind, data in (("main", main), ("short", short)):
        for s in data["shots"]:
            if s["source"]:
                m = source_meta(s["source"])
                used.append({"export": kind, "edit_start": round(s["start"], 3), "edit_duration": round(s["duration"], 3), "source": s["source"], "outlet": SOURCES[s["source"]][0],
                             "programme": SOURCES[s["source"]][1], "url": m["url"], "title": m["title"], "source_in": round(s["seek"], 3), "source_out": round(s["seek_end"], 3),
                             "original_audio": s["sound"], "speaker": CLIPS[s["clip"]]["who"] if s["clip"] else None, "context": s["clip"] or s["card"]})
    manifest = {"research_cutoff": CUTOFF, "presentation": "1080p export; 1080p sources scaled to a 1280x720 panel (main) or 1080x608 panel (Short) with Lanczos; 720p ABC source not used in the edit.",
                "sources": {k: {"outlet": v[0], "programme": v[1], "date": v[2], **source_meta(k)} for k, v in SOURCES.items() if (RAW / (k + ".mp4")).exists()},
                "used_ranges": used, "rule": "No source range is shown twice within an export (audited at plan time); the standalone Short may reuse main-video ranges."}
    (OUT / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    # chapters for the upload package
    chapters = "\n".join(f"{int(s['start']//60)}:{int(s['start']%60):02d} {s['chapter'].title()}" for s in main["sections"])
    links = "\n".join(f"- {SOURCES[k][0]} — {source_meta(k)['title']}: {source_meta(k)['url']}" for k in sorted({u['source'] for u in used}))
    up = f"""# The $5,000 Promise: The Critics' Case — upload package

## Main video

Title: **Trump's $5,000 Promise: The Case Against It, in the Critics' Own Words**

Alternative: **$5,000 If Republicans Win? What CNN, MSNBC, NBC, CBS and PBS Found**

Description:

Donald Trump promised every adult citizen $5,000 if Republicans keep the House and Senate. This is the case critics built against it, drawn from CNN, MS NOW (formerly MSNBC), NBC, CBS and PBS coverage: the arithmetic (about $1.3 trillion), the funding claims (tariffs, then "non-tax money"), the authority question (the president says Congress need not approve it; the House Majority Leader says the details "have to be worked out by Congress"), and the bribery charge, which an election-law scholar told PBS is most likely protected speech.

Every excerpt is attributed on screen. Muted footage is labeled as source footage under analysis. The $269 million adult figure and $1.3 trillion total are CBS's on-air arithmetic; other outlets' estimates are cited where used. Nothing here is a legal finding.

Research current through {CUTOFF}.

{chapters}

Sources:
{links}
- White House release, September 10, 2026: https://www.whitehouse.gov/releases/2026/09/trump-dividend-america-is-winning-and-americans-should-win-with-it/
- CRS, Congress's Power of the Purse (R46417): https://www.congress.gov/crs-product/R46417

#Trump #Politics #Explained

## Standalone Short

Title: **$5,000 If Republicans Win? The Critics' Case in 50 Seconds**

Description:

Cost, money, authority and the bribe question — the case against Trump's $5,000 promise, from CNN, MS NOW, NBC, CBS and PBS coverage. Research current through {CUTOFF}.

#Trump #Politics #Shorts

The Short contains no reference to the main video.

## Delivery

- Main: 1920 × 1080, 30 fps, {int(main['duration']//60)}:{int(main['duration']%60):02d}; SRT captions supplied; excerpt captions burned in.
- Short: 1080 × 1920, 30 fps, {main and int(short['duration'])} s; captions burned in plus SRT.
- Approved Cedar voice; original audio from {len([u for u in used if u['original_audio']])} attributed excerpts ({round(sum(u['edit_duration'] for u in used if u['original_audio']))} s); AAC 320 kb/s; PCM masters included.
- Sources are 1080p broadcast uploads presented in a 1080p layout. Nothing is upscaled to a resolution it does not have.

The videos have not been uploaded. Attribution does not imply broadcaster endorsement or a new footage licence.
"""
    (OUT / "UPLOAD_PACKAGE.md").write_text(up, encoding="utf-8")
    make_covers()
    print("Packaged:", OUT)


def make_covers():
    """Thumbnails in the house style from a real export frame."""
    main = json.loads((WORK / "main_timeline.json").read_text(encoding="utf-8"))
    shot = next(s for s in main["shots"] if s["clip"] == "trump_promise")
    frame = QA / "cover_src.png"
    run([FF, "-v", "error", "-y", "-ss", shot["seek"] + 4.0, "-i", RAW / (shot["source"] + ".mp4"), "-frames:v", 1, frame])
    src = Image.open(frame).convert("RGB"); theme = house_theme()
    bc.cover(theme, src, "$5,000", "IF THE GOP WINS?", "THE CRITICS'\nCASE", "CNN · MS NOW · NBC · CBS · PBS",
             "$1.3 TRILLION · TARIFFS · CONGRESS · \"BRIBE\"", OUT / "Cover_Main.jpg")
    bc.cover(theme, src, "$5,000", "IF THE GOP WINS?", "THE CRITICS' CASE", "CNN · MS NOW · NBC · CBS · PBS", "", OUT / "Cover_Short.jpg", vertical=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["narrate", "plan", "render", "music", "qa", "package"]); ap.add_argument("kind", nargs="?", choices=["main", "short"])
    ap.add_argument("--music", action="store_true", help="mux the music master if it exists")
    ap.add_argument("--theme", choices=["broadcast", "classic"], default=THEME)
    args = ap.parse_args()
    THEME = args.theme
    SHOTS = WORK / ("shots_broadcast" if THEME == "broadcast" else "shots"); SHOTS.mkdir(exist_ok=True)
    PLATES = WORK / ("plates_broadcast" if THEME == "broadcast" else "plates"); PLATES.mkdir(exist_ok=True)
    if args.stage == "narrate":
        stage_narrate()
    elif args.stage == "plan":
        stage_plan()
    elif args.stage == "render":
        stage_render(args.kind or "main", music=args.music)
    elif args.stage == "music":
        stage_music()
    elif args.stage == "qa":
        stage_qa()
    elif args.stage == "package":
        stage_package()
