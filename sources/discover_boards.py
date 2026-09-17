#!/usr/bin/env python
"""Probe candidate slugs against all three ATS and keep the ones that are live.

Company ATS slugs are not published anywhere central, and companies migrate
between platforms, so the registry has to be built and re-verified by probing.
Run this periodically; it only adds boards that actually return jobs.
"""
import concurrent.futures as cf, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from sources.ats import fetch

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "boards.json"

CANDIDATES = """
razorpay razorpaysoftwareprivatelimited zerodha groww cred phonepe paytm meesho swiggy zomato
zeta juspay slice jupiter navi acko policybazaar upstox angelone smallcase
freshworks zoho chargebee postman browserstack hasura clevertap whatfix mindtickle
innovaccer darwinbox eightfoldai sprinklr icertis capillarytech locus netradyne
sarvam krutrim sarvamai glean atlan hyperverge mad-street-den observeai
dream11 dreamsports games24x7 mpl unacademy byjus vedantu physicswallah
delhivery rivigo blackbuck porter zepto blinkit dunzo urbancompany
sharechat koo inmobi glance flipkart myntra nykaa lenskart boat
uber airbnb stripe plaid ramp rippling databricks snowflake confluent
mongodb elastic hashicorp gitlab cloudflare datadog atlassian canva figma
notion airtable linear vercel netlify supabase anthropic openai scale
spotify shopify doordash instacart robinhood coinbase affirm chime brex
mercury deel remote gusto carta addepar samsara verkada nuro waymo
harness postman-labs sprinto chargebeeinc turing arcesium quantiphi
tekion moengage netcore exotel knowlarity kaleyra gupshup

razorpaysoftwareprivatelimited swiggyin zomatoin phonepeinternalhiring flipkartcareers sprinklrindia freshworksinc zohocorp browserstackinc postmanlabs hasurahq dreamsports dream11 games24x7india mpl unacademyindia byjusindia vedantuinnovations licious rebelfoods bigbasket country-delight wakefit pristyncare practo cultfit curefit healthifyme mfine tataneu jiohaptik haptik yellowai gupshupio setuhq decentro cashfree pinelabs bharatpe khatabook okcredit indiagold zetasuite m2p perfios signzy idfy hyperface falconx ola olaelectric ather simpleenergy ultraviolette euler-motors arcesium quantiphi tigeranalytics fractalanalytics mutinex latentview clearfeed devrev nutanix icertis rubrik cohesity druva sarvamai krutrim ai4bharat corover haptikai uniphore observe zluri whatfix mindtickleinc leadsquared kaleyra exotel knowlarity darwinbox keka springworks zimyo peoplestrong juspaytechnologies innoviti mswipe ezetap worldline jupitermoney fi-money epifi smallcaseHQ tickertape sensibull dhan scaler newtonschool masaischool codingninjas geeksforgeeks turingcom deel-india gitlabinc remotecom
""".split()

ATS = ("greenhouse", "lever", "ashby")


def probe(slug):
    hits = []
    for board in ATS:
        jobs, err = fetch(board, slug)
        if jobs:
            hits.append({"board": board, "slug": slug, "jobs": len(jobs),
                         "company": jobs[0]["company"]})
    return hits


def main():
    found = []
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        for hits in ex.map(probe, CANDIDATES):
            for h in hits:
                found.append(h)
                print(f"  live  {h['board']:11s} {h['slug']:32s} {h['jobs']:4d} jobs")

    # merge with anything already registered, newest count wins
    existing = {}
    if REGISTRY.exists():
        existing = {(b["board"], b["slug"]): b for b in json.loads(REGISTRY.read_text())}
    for h in found:
        existing[(h["board"], h["slug"])] = h
    boards = sorted(existing.values(), key=lambda b: (b["board"], b["slug"]))
    REGISTRY.write_text(json.dumps(boards, indent=2) + "\n")

    print(f"\n{len(found)} live boards from {len(CANDIDATES)} candidates"
          f"  ->  registry now holds {len(boards)}")
    print(f"total open roles visible: {sum(b['jobs'] for b in boards):,}")


if __name__ == "__main__":
    main()
