"use client";

import { useEffect, useMemo, useState } from "react";

type SpendCondition = {
  amount: number;
  currency: string;
  period: string;
  description: string;
};

type Lounge = {
  airport_code: string;
  terminal: string;
  lounge_name: string;
};

type CardRecord = {
  id: string;
  card_name: string;
  issuer: string;
  network: string;
  primary_card: {
    quarterly_visit_limit: number | null;
    spend_conditions: SpendCondition[];
  };
  add_on_card_rule: "shared_quota" | "independent_quota" | "no_access";
  eligible_lounges: Lounge[];
  last_verified: string;
  source_url?: string;
};

type CardsResponse = { cards: CardRecord[] };

const quotaDescriptions: Record<CardRecord["add_on_card_rule"], string> = {
  shared_quota: "Add-on visits draw from the primary card’s shared allowance.",
  independent_quota: "Add-on card has its own separate visit allowance.",
  no_access: "Add-on cards are not eligible for lounge access under this record.",
};

function formatAmount(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

function verifiedDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Verification date unavailable";
  return `Verified ${new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date)}`;
}

export default function Home() {
  const [cards, setCards] = useState<CardRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [issuer, setIssuer] = useState("");
  const [cardId, setCardId] = useState("");
  const [cardholder, setCardholder] = useState<"primary" | "addon">("primary");
  const [airportCode, setAirportCode] = useState("");
  const [terminal, setTerminal] = useState("");
  const [spend, setSpend] = useState("");
  const [usedVisits, setUsedVisits] = useState("");
  const [hasChecked, setHasChecked] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/cards")
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load the card directory.");
        return (await response.json()) as CardsResponse;
      })
      .then((data) => {
        if (!active) return;
        const records = Array.isArray(data.cards) ? data.cards : [];
        setCards(records);
        setIssuer(records[0]?.issuer ?? "");
        setCardId(records[0]?.id ?? "");
      })
      .catch(() => {
        if (active) setLoadError("Card data could not be loaded. Check the data/cards.json file and reload.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const issuers = useMemo(() => [...new Set(cards.map((card) => card.issuer))], [cards]);
  const issuerCards = useMemo(() => cards.filter((card) => card.issuer === issuer), [cards, issuer]);
  const selectedCard = cards.find((card) => card.id === cardId);
  const airportOptions = useMemo(
    () => [...new Set((selectedCard?.eligible_lounges ?? []).map((lounge) => lounge.airport_code))],
    [selectedCard],
  );
  const terminalOptions = useMemo(
    () =>
      [...new Set(
        (selectedCard?.eligible_lounges ?? [])
          .filter((lounge) => lounge.airport_code.toUpperCase() === airportCode.trim().toUpperCase())
          .map((lounge) => lounge.terminal),
      )],
    [selectedCard, airportCode],
  );

  const matchingLounges = (selectedCard?.eligible_lounges ?? []).filter(
    (lounge) =>
      lounge.airport_code.toUpperCase() === airportCode.trim().toUpperCase() &&
      lounge.terminal.toLowerCase() === terminal.trim().toLowerCase(),
  );
  const hasLocation = Boolean(airportCode.trim() && terminal.trim());
  const spendRequirement = selectedCard?.primary_card.spend_conditions[0];
  const spendValue = spend === "" ? null : Number(spend);
  const spendMet = !spendRequirement || spendValue === null || spendValue >= spendRequirement.amount;
  const visitLimit = selectedCard?.primary_card.quarterly_visit_limit ?? null;
  const visitCount = usedVisits === "" ? null : Number(usedVisits);
  const remainingVisits = visitLimit === null || visitCount === null ? null : Math.max(0, visitLimit - visitCount);

  let verdict: "yes" | "no" | "unknown" = "unknown";
  let verdictMessage = "Enter a terminal to check your lounge options.";
  if (selectedCard && cardholder === "addon" && selectedCard.add_on_card_rule === "no_access") {
    verdict = "no";
    verdictMessage = "This card’s recorded add-on policy does not include lounge access.";
  } else if (hasLocation && selectedCard) {
    if (matchingLounges.length > 0) {
      if (!spendMet) {
        verdict = "no";
        verdictMessage = "The preceding-quarter spend requirement has not been met.";
      } else if (remainingVisits === 0) {
        verdict = "no";
        verdictMessage = "The recorded quarterly visit allowance has been used.";
      } else if (visitLimit !== null && visitCount === null) {
        verdict = "unknown";
        verdictMessage = "Add visits already used to confirm your remaining allowance.";
      } else if (spendRequirement && spendValue === null) {
        verdict = "unknown";
        verdictMessage = "Add preceding-quarter eligible spend to confirm this benefit.";
      } else {
        verdict = "yes";
        verdictMessage = "A matching lounge is listed for this airport and terminal.";
      }
    } else if (selectedCard.eligible_lounges.length > 0) {
      verdict = "no";
      verdictMessage = "No lounge is listed for this airport and terminal.";
    } else {
      verdict = "unknown";
      verdictMessage = "No airport-terminal lounge list is on file for this card yet.";
    }
  }

  const shownVerdict = hasChecked ? verdict : "unknown";
  const shownVerdictMessage = hasChecked
    ? hasLocation
      ? verdictMessage
      : "Enter both an airport code and terminal, then check again."
    : "Choose your card and airport details, then check your access.";

  function checkEligibility() {
    setHasChecked(true);
  }

  function updateIssuer(value: string) {
    setHasChecked(false);
    setIssuer(value);
    const firstCard = cards.find((card) => card.issuer === value);
    setCardId(firstCard?.id ?? "");
    setAirportCode("");
    setTerminal("");
  }

  function updateCard(value: string) {
    setHasChecked(false);
    setCardId(value);
    setAirportCode("");
    setTerminal("");
  }

  return (
    <main className="min-h-screen pb-12">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Gatewise home">
          <span className="brand-mark" aria-hidden="true">G</span>
          <span>gatewise<span className="brand-period">.</span></span>
        </a>
        <div className="topbar-right">
          <span className="live-dot" />
          <span>India lounge directory</span>
          <span className="topbar-divider" />
          <span className="topbar-date">Issuer terms · verify before travel</span>
        </div>
      </header>

      <section id="home" className="hero-shell">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-line" /> TRAVEL, WITHOUT THE GUESSWORK</div>
          <h1>Your next lounge,<br /><span>already figured out.</span></h1>
          <p className="hero-description">Check your card benefits before you reach the airport. Clear rules, fewer surprises at the gate.</p>
          <div className="hero-proof">
            <span className="proof-icon" aria-hidden="true">✳</span>
            <span>Built around issuer-published card terms</span>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="plane-path">· · · · · · · · · · · · · · · ·</div>
          <div className="art-sun" />
          <div className="art-plane">✈</div>
          <div className="art-label label-one"><span>✦</span> Lounge access</div>
          <div className="art-label label-two">INR <b>₹</b></div>
          <div className="art-coordinates">19°05′N&nbsp; 72°52′E<br />TERMINAL 2</div>
        </div>
      </section>

      <section className="workspace" aria-label="Lounge eligibility checker">
        <div className="section-heading">
          <div>
            <div className="eyebrow section-eyebrow"><span className="eyebrow-line" /> THE LOUNGE CHECKER</div>
            <h2>Find your access</h2>
          </div>
          <div className="data-status"><span className="status-dot" /> {loading ? "Loading card directory" : "Card directory connected"}</div>
        </div>

        {loadError && <div className="load-error" role="alert">{loadError}</div>}

        <div className="checker-grid">
          <section className="form-card" aria-labelledby="details-title">
            <div className="card-heading">
              <span className="step-number">01</span>
              <div><h3 id="details-title">Your card details</h3><p>Choose the card you’ll be presenting.</p></div>
            </div>
            <div className="field-grid">
              <label className="field field-wide">
                <span>Bank / issuer</span>
                <select value={issuer} onChange={(event) => updateIssuer(event.target.value)} disabled={loading || issuers.length === 0}>
                  {issuers.length === 0 && <option value="">No issuers available</option>}
                  {issuers.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <label className="field field-wide">
                <span>Credit card</span>
                <select value={cardId} onChange={(event) => updateCard(event.target.value)} disabled={!issuerCards.length}>
                  {issuerCards.map((card) => <option key={card.id} value={card.id}>{card.card_name}</option>)}
                </select>
              </label>
              <fieldset className="field field-wide cardholder-field">
                <legend>Cardholder type</legend>
                <div className="segmented-control">
                  <button type="button" className={cardholder === "primary" ? "segment active" : "segment"} onClick={() => { setCardholder("primary"); setHasChecked(false); }} aria-pressed={cardholder === "primary"}>Primary card</button>
                  <button type="button" className={cardholder === "addon" ? "segment active" : "segment"} onClick={() => { setCardholder("addon"); setHasChecked(false); }} aria-pressed={cardholder === "addon"}>Add-on card</button>
                </div>
              </fieldset>
            </div>

            <div className="form-divider" />
            <div className="card-heading location-heading">
              <span className="step-number">02</span>
              <div><h3>Where are you flying from?</h3><p>Match the airport and terminal on your itinerary.</p></div>
            </div>
            <div className="field-grid location-fields">
              <label className="field">
                <span>Airport code</span>
                <input list="airport-codes" value={airportCode} onChange={(event) => { setAirportCode(event.target.value.toUpperCase()); setTerminal(""); setHasChecked(false); }} placeholder="e.g. BOM" maxLength={4} autoCapitalize="characters" />
                <datalist id="airport-codes">{airportOptions.map((code) => <option key={code} value={code} />)}</datalist>
              </label>
              <label className="field">
                <span>Terminal</span>
                <input list="terminal-options" value={terminal} onChange={(event) => { setTerminal(event.target.value); setHasChecked(false); }} placeholder="e.g. T2" />
                <datalist id="terminal-options">{terminalOptions.map((value) => <option key={value} value={value} />)}</datalist>
              </label>
            </div>
            <p className="field-hint"><span aria-hidden="true">ⓘ</span> Use the airport code and terminal shown on your boarding pass. Suggestions appear when lounge locations are on file.</p>
            <button type="button" className="check-button" onClick={checkEligibility}>
              Check eligibility <span aria-hidden="true">→</span>
            </button>
          </section>

          <aside className={`result-card result-${shownVerdict}`} aria-live="polite" aria-label="Eligibility result">
            <div className="result-topline"><span>YOUR ACCESS CHECK</span><span className="result-orbit-icon" aria-hidden="true">↗</span></div>
            <div className="verdict-block">
              <span className={`verdict-icon verdict-icon-${shownVerdict}`} aria-hidden="true">{shownVerdict === "yes" ? "✓" : shownVerdict === "no" ? "×" : "?"}</span>
              <div className="verdict-label">{shownVerdict === "yes" ? "YOU’RE IN" : shownVerdict === "no" ? "NOT ELIGIBLE" : "NOT CONFIRMED"}</div>
              <p>{shownVerdictMessage}</p>
            </div>
            <div className="result-divider" />
            <div className="result-location">
              <span className="result-icon" aria-hidden="true">⌖</span>
              <div><span className="result-caption">SELECTED LOCATION</span><strong>{airportCode.trim() || "Airport"}{airportCode.trim() && terminal.trim() ? ` · ${terminal.trim()}` : terminal.trim() ? ` · ${terminal.trim()}` : " · Terminal"}</strong></div>
            </div>
            {matchingLounges.length > 0 && <div className="matched-lounges">{matchingLounges.map((lounge) => <div key={`${lounge.airport_code}-${lounge.terminal}-${lounge.lounge_name}`} className="lounge-row"><span>✦</span>{lounge.lounge_name}</div>)}</div>}
            <div className="result-footnote">{selectedCard ? verifiedDate(selectedCard.last_verified) : "Card information unavailable"}</div>
          </aside>
        </div>

        <div className="details-grid">
          <section className="detail-card" aria-labelledby="spend-title">
            <div className="detail-card-top"><span className="detail-icon spend-icon" aria-hidden="true">₹</span><span className="detail-kicker">BENEFIT CONDITIONS</span></div>
            <h3 id="spend-title">Spend to unlock</h3>
            {spendRequirement ? <>
              <div className="spend-amount">{formatAmount(spendRequirement.amount, spendRequirement.currency)}<span> / quarter</span></div>
              <p className="detail-copy">{spendRequirement.description}</p>
              <label className="field spend-input"><span>Your eligible spend · INR</span><input type="number" min="0" inputMode="numeric" value={spend} onChange={(event) => { setSpend(event.target.value); setHasChecked(false); }} placeholder="Enter amount" /></label>
              {spendValue !== null && <div className={spendMet ? "inline-state state-good" : "inline-state state-warn"}>{spendMet ? "✓ Spend threshold met" : `₹${Math.max(0, spendRequirement.amount - spendValue).toLocaleString("en-IN")} more needed`}</div>}
            </> : <p className="detail-copy">No quarterly spend condition is listed for this card. Check the issuer’s latest terms before travel.</p>}
          </section>

          <section className="detail-card" aria-labelledby="quota-title">
            <div className="detail-card-top"><span className="detail-icon quota-icon" aria-hidden="true">↻</span><span className="detail-kicker">VISIT ALLOWANCE</span></div>
            <h3 id="quota-title">Know your quota</h3>
            <div className="quota-summary"><strong>{visitLimit === null ? "—" : visitLimit}</strong><span> visits<br />per quarter</span><span className="quota-divider" /><strong>{remainingVisits === null ? "—" : remainingVisits}</strong><span>estimated<br />remaining</span></div>
            <p className="detail-copy">{selectedCard ? quotaDescriptions[selectedCard.add_on_card_rule] : "Select a card to view its add-on policy."}</p>
            {visitLimit !== null && <label className="field spend-input"><span>Visits already used this quarter</span><input type="number" min="0" max={visitLimit} inputMode="numeric" value={usedVisits} onChange={(event) => { setUsedVisits(event.target.value); setHasChecked(false); }} placeholder="Enter visits used" /></label>}
          </section>

          <section className="detail-card entry-card" aria-labelledby="entry-title">
            <div className="detail-card-top"><span className="detail-icon entry-icon" aria-hidden="true">↗</span><span className="detail-kicker">AT THE AIRPORT</span></div>
            <h3 id="entry-title">Your entry, step by step</h3>
            <ol className="entry-steps">
              <li><span>1</span><p>Check that your airport and terminal match an eligible lounge in the list.</p></li>
              <li><span>2</span><p>Show your boarding pass and the eligible credit card at the lounge desk.</p></li>
              <li><span>3</span><p>Ask staff to confirm complimentary access before they process the card.</p></li>
              <li><span>4</span><p>Keep the transaction slip and confirm the visit was charged as complimentary.</p></li>
            </ol>
          </section>
        </div>

        <footer className="page-footer">
          <div className="footer-mark"><span className="brand-mark" aria-hidden="true">G</span><span>gatewise<span className="brand-period">.</span></span></div>
          <p>Access terms and lounge availability can change. Confirm with your card issuer and the lounge before travel.</p>
          {selectedCard?.source_url && <a href={selectedCard.source_url} target="_blank" rel="noreferrer">Issuer terms <span aria-hidden="true">↗</span></a>}
        </footer>
      </section>
    </main>
  );
}
