// const state={domain:"transaction",records:{transactions:[],loans:[]},selected:null,latest:null};
// const $=id=>document.getElementById(id);
// async function getJSON(path,options){const r=await fetch(path,options);const d=await r.json();if(!r.ok)throw new Error(d.error||"Request failed");return d;}
// function currency(v){return new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:0}).format(Number(v||0));}
// function renderRecords(){
//   const list=state.domain==="loan"?state.records.loans:state.records.transactions;
//   $("recordCount").textContent=state.records.transactions.length+state.records.loans.length;
//   $("recordList").innerHTML=list.map(r=>{
//     const loan=state.domain==="loan",headline=loan?currency(r.loanAmount):currency(r.amount);
//     const sub=loan?`${r.employmentType} · LTV ${r.loanToValue}% · credit history ${r.creditHistory?"positive":"limited"}`:`${r.type} · ${r.location} · origin ${r.nameOrig}`;
//     return `<article class="record ${state.selected?.id===r.id?"selected":""}" data-id="${r.id}"><div class="record-top"><span class="record-id">${r.id}</span><strong>${headline}</strong></div><div class="record-sub">${sub}</div></article>`;
//   }).join("");
//   document.querySelectorAll(".record").forEach(el=>el.addEventListener("click",()=>{state.selected=list.find(r=>r.id===el.dataset.id);renderRecords();runSelected();}));
// }
// async function loadRecords(){state.records=await getJSON("/api/records");renderRecords();}
// async function loadHistory(){
//   const rows=(await getJSON("/api/decisions")).decisions||[];
//   if(!rows.length){$("history").innerHTML='<div class="muted">No assessments stored yet.</div>';return;}
//   $("history").innerHTML=rows.map(r=>{const label=r.domain==="loan"?"Loan":"Transaction",pct=Math.round(Number(r.score)*100),date=new Date(r.created_at).toLocaleString("en-IN",{dateStyle:"medium",timeStyle:"short"});return `<div class="history-row"><div><div class="history-id">${r.record_id}</div><div class="history-meta">${label} · ${date}</div></div><div>${pct}% risk</div><div class="history-meta">${r.reason_code}</div><div><span class="decision ${r.action}">${r.action.toUpperCase()}</span></div></div>`}).join("");
// }
// function setMode(domain){
//   state.domain=domain;state.selected=null;state.latest=null;
//   document.querySelectorAll(".mode").forEach(b=>b.classList.toggle("active",b.dataset.domain===domain));
//   $("emptyState").classList.remove("hidden");$("resultState").classList.add("hidden");
//   $("decisionBadge").textContent="WAITING";$("decisionBadge").className="decision neutral";renderRecords();
//   $("voiceStatus").textContent=domain==="loan"?"Choose a sample loan application to assess default risk.":"Choose a sample transaction to assess fraud risk.";
// }
// async function runSelected(){
//   if(!state.selected)return;
//   $("voiceStatus").textContent="Running all five stages...";
//   try{
//     const result=await getJSON("/api/score",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({domain:state.domain,record:state.selected})});
//     state.latest=result;const pct=Math.round(result.score.score*100);
//     $("scoreValue").textContent=pct+"%";$("reasonCode").textContent=result.score.reason_code;$("explanationText").textContent=result.explanation;
//     const badge=$("decisionBadge");badge.textContent=result.action.toUpperCase();badge.className="decision "+result.action;
//     $("emptyState").classList.add("hidden");$("resultState").classList.remove("hidden");$("voiceStatus").textContent=`Assessment complete for ${result.record.id}.`;
//     await loadHistory();
//   }catch(e){$("voiceStatus").textContent=e.message;}
// }
// function answerQuestion(qtext){
//   if(!state.latest){$("voiceStatus").textContent="Assess a record first, then ask why it was flagged.";return;}
//   const q=qtext.toLowerCase(),r=state.latest;
//   if(q.includes("why")||q.includes("reason")||q.includes("flag")){$("explanationText").textContent=r.explanation;$("voiceStatus").textContent=`The main signals were ${(r.score.factors||[]).join(", ")||"the configured risk rules"}.`;return;}
//   if(q.includes("action")||q.includes("decision")||q.includes("what happens")){const v=r.action==="block"?"blocked":r.action==="deny"?"denied":r.action;$("voiceStatus").textContent=`The current prototype decision is to ${v} this ${r.domain}.`;return;}
//   if(q.includes("score")||q.includes("risk")){$("voiceStatus").textContent=`The estimated risk is ${Math.round(r.score.score*100)}%.`;return;}
//   $("voiceStatus").textContent="Try asking: why was this flagged, what is the risk score, or what is the decision?";
// }
// function speak(t){if(!("speechSynthesis"in window)){$("voiceStatus").textContent="Text-to-speech is not available in this browser.";return;}window.speechSynthesis.cancel();window.speechSynthesis.speak(new SpeechSynthesisUtterance(t));}
// function startVoiceInput(){
//   const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
//   if(!Recognition){$("voiceStatus").textContent="Voice input is not supported in this browser. Type your question instead.";return;}
//   const rec=new Recognition();rec.lang="en-IN";rec.interimResults=false;rec.maxAlternatives=1;$("voiceStatus").textContent="Listening...";
//   rec.onresult=e=>{const t=e.results[0][0].transcript;$("question").value=t;answerQuestion(t);};
//   rec.onerror=()=>{$("voiceStatus").textContent="Voice input could not be captured. Type your question instead.";};rec.start();
// }
// document.querySelectorAll(".mode").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.domain)));
// $("askBtn").addEventListener("click",()=>answerQuestion($("question").value.trim()));
// $("question").addEventListener("keydown",e=>{if(e.key==="Enter")answerQuestion($("question").value.trim());});
// $("refreshBtn").addEventListener("click",async()=>{await loadRecords();await loadHistory();});
// $("runAgainBtn").addEventListener("click",runSelected);
// $("speakBtn").addEventListener("click",()=>{if(state.latest)speak(state.latest.explanation+" Decision: "+state.latest.action+".");});
// $("micBtn").addEventListener("click",startVoiceInput);
// (async function(){try{await loadRecords();await loadHistory();$("voiceStatus").textContent="Select a sample transaction to start the demo.";}catch(e){$("voiceStatus").textContent="Unable to initialize demo data: "+e.message;}})();


const state = {
  domain: "manufacturing",
  records: {
    transactions: [],
    loans: [],
    manufacturing: []
  },
  selected: null,
  latest: null,
  replaying: false
};

const $ = id => document.getElementById(id);


async function getJSON(path, options) {
  const r = await fetch(path, options);
  let d = {};

  try {
    d = await r.json();
  } catch (e) {
    /* non-JSON error body */
  }

  if (!r.ok) {
    throw new Error(d.detail || d.error || "Request failed");
  }

  return d;
}


function currency(v) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format(Number(v || 0));
}


function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}


/* Manufacturing display helpers */

const ASSET_LABELS = {
  machine_tool: "CNC machine tool",
  metro_compressor: "Metro compressor",
  turbofan_engine: "Turbofan engine",
  bearing: "Bearing"
};

const MODE_COPY = {
  manufacturing: {
    eyebrow: "AI BUILDER CUP HACKATHON PROTOTYPE (MANUFACTURING)",
    title: "Voice-First Predictive Maintenance Copilot",
    sub: "Sensor readings in, failure risk out: ML prediction, Gemini diagnosis grounded in the maintenance manual, and a work order, through one shared five-stage pipeline.",
    models: ["4", "machine, compressor, engine, bearing"],
    score: "Failure probability",
    explanation: "GEMINI DIAGNOSIS (GROUNDED IN THE MAINTENANCE MANUAL)",
    status: "Choose a machine to assess its failure risk."
  },
  transaction: {
    eyebrow: "AI BUILDER CUP HACKATHON PROTOTYPE (BFSI)",
    title: "Voice-First Fraud & Risk Assistant",
    sub: "One shared five-stage pipeline for transaction fraud and loan applicant risk.",
    models: ["2", "fraud + loan risk"],
    score: "Risk score",
    explanation: "PLAIN-LANGUAGE EXPLANATION",
    status: "Choose a sample transaction to assess fraud risk."
  },
  loan: {
    eyebrow: "AI BUILDER CUP HACKATHON PROTOTYPE (BFSI)",
    title: "Voice-First Fraud & Risk Assistant",
    sub: "One shared five-stage pipeline for transaction fraud and loan applicant risk.",
    models: ["2", "fraud + loan risk"],
    score: "Risk score",
    explanation: "PLAIN-LANGUAGE EXPLANATION",
    status: "Choose a sample loan application to assess default risk."
  }
};


function mfgSummary(r) {

  const n = (v, d = 1) => Number(v).toFixed(d);

  switch (r.asset) {

    case "metro_compressor":
      return `TP2 ${n(r.TP2)} bar · motor ${n(r.Motor_current)} A · oil ${n(r.Oil_temperature)} °C`;

    case "turbofan_engine":
      return `${r.cycle !== undefined ? "cycle " + n(r.cycle, 0) + " · " : ""}s4 ${n(r.s4, 0)} · s11 ${n(r.s11, 2)} · s15 ${n(r.s15, 2)}`;

    case "bearing":
      return `drive-end RMS ${n(r.de_rms, 3)} · kurtosis ${n(r.de_kurtosis)} · crest ${n(r.de_crest)}`;

    default:
      return `tool wear ${n(r["Tool wear"], 0)} min · torque ${n(r.Torque)} Nm · ${n(r["Rotational speed"], 0)} rpm`;
  }
}


function isMfg() {
  return state.domain === "manufacturing";
}


function currentList() {
  if (isMfg()) return state.records.manufacturing;
  return state.domain === "loan"
    ? state.records.loans
    : state.records.transactions;
}


/* =========================================================
   RECORD LIST
   ========================================================= */

function renderRecords() {

  const list = currentList();

  $("recordCount").textContent = list.length;

  $("recordList").innerHTML = list.map(r => {

    const loan = state.domain === "loan";

    const headline = isMfg()
      ? esc(ASSET_LABELS[r.asset] || r.asset)
      : loan
        ? currency(r.loanAmount)
        : currency(r.amount);

    const sub = isMfg()
      ? esc(mfgSummary(r))
      : loan
        ? `${r.employmentType} · LTV ${r.loanToValue}% · credit history ${r.creditHistory ? "positive" : "limited"}`
        : `${r.type} · ${r.location} · origin ${r.nameOrig}`;

    return `
      <article
        class="record ${state.selected?.id === r.id ? "selected" : ""}"
        data-id="${esc(r.id)}"
      >

        <div class="record-top">
          <span class="record-id">${esc(r.id)}</span>
          <strong>${headline}</strong>
        </div>

        <div class="record-sub">
          ${sub}
        </div>

      </article>
    `;

  }).join("");


  document.querySelectorAll(".record").forEach(el => {

    el.addEventListener("click", () => {

      state.selected =
        list.find(r => r.id === el.dataset.id);

      renderRecords();

      runSelected();

    });

  });

}


/* =========================================================
   LOAD RECORDS
   ========================================================= */

async function loadRecords() {

  if (isMfg()) {

    const data = await getJSON("/api/records?domain=manufacturing");

    state.records.manufacturing = data.records || [];

  } else {

    const data = await getJSON("/api/records");

    state.records.transactions = data.transactions || [];

    state.records.loans = data.loans || [];

  }

  renderRecords();

}


/* =========================================================
   REASON CODE → HUMAN READABLE LABEL
   ========================================================= */

function humanizeReason(code) {

  const labels = {

    HIGH_AMOUNT_AND_BALANCE_ANOMALY:
      "Amount & balance anomaly",

    ELEVATED_TRANSFER_OR_CASHOUT_PATTERN:
      "Elevated transfer / cash-out pattern",

    LOW_RISK_TRANSACTION:
      "Low-risk transaction",

    HIGH_LTV_AND_CREDIT_RISK:
      "High LTV & credit risk",

    ELEVATED_CREDIT_OR_AFFORDABILITY_RISK:
      "Elevated credit / affordability risk",

    LOW_RISK_APPLICANT:
      "Low-risk applicant"

  };


  return labels[code]
    || String(code || "Risk signal")
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, m => m.toUpperCase());

}


/* =========================================================
   DECISION HISTORY
   ========================================================= */

async function loadHistory() {

  const rows =
    (await getJSON("/api/decisions")).decisions || [];


  /* Empty state */

  if (!rows.length) {

    $("history").innerHTML = `
      <div class="history-empty">

        <div class="history-empty-icon">
          ✓
        </div>

        <div>
          <strong>No assessments stored yet</strong>

          <span>
            Completed risk assessments will appear here.
          </span>
        </div>

      </div>
    `;

    return;
  }


  /* History rows */

  $("history").innerHTML = rows.map(r => {

    const isLoan =
      r.domain === "loan";

    const isMachine =
      r.domain === "manufacturing" || r.domain === "sensor";

    const label =
      isMachine ? "Machine" : isLoan ? "Loan" : "Transaction";

    const icon =
      isMachine ? "MFG" : isLoan ? "LOAN" : "TXN";

    const iconClass =
      isMachine ? "manufacturing" : isLoan ? "loan" : "transaction";

    const pct =
      Math.round(Number(r.score) * 100);

    const action =
      String(r.action || "").toLowerCase();

    const date =
      new Date(r.created_at).toLocaleString(
        "en-IN",
        {
          dateStyle: "medium",
          timeStyle: "short"
        }
      );


    /* Risk severity */

    const riskClass =
      pct >= 70
        ? "high"
        : pct >= 30
          ? "medium"
          : "low";


    const reason =
      humanizeReason(r.reason_code);


    return `

      <article class="history-row">

        <!-- CASE -->

        <div class="history-case">

          <div class="case-icon ${iconClass}">
            ${icon}
          </div>


          <div class="history-case-copy">

            <div class="history-id">
              ${esc(r.record_id)}
            </div>

            <div class="history-meta">

              ${label}

              <span class="meta-dot">
                •
              </span>

              ${date}

            </div>

          </div>

        </div>


        <!-- RISK -->

        <div class="history-risk">

          <div class="risk-top">

            <strong>
              ${pct}%
            </strong>

            <span>
              risk
            </span>

          </div>


          <div class="risk-track">

            <span
              class="risk-fill ${riskClass}"
              style="width:${Math.min(pct, 100)}%"
            ></span>

          </div>

        </div>


        <!-- KEY SIGNAL -->

        <div class="history-reason">

          <span class="reason-label">
            KEY SIGNAL
          </span>


          <strong>
            ${reason}
          </strong>


          <span class="reason-code-small">
            ${esc(r.reason_code || "")}
          </span>

        </div>


        <!-- DECISION -->

        <div class="history-decision">

          <span class="decision ${action}">
            ${esc(String(r.action || "").replaceAll("_", " ").toUpperCase())}
          </span>

        </div>

      </article>

    `;

  }).join("");

}


/* =========================================================
   MODE SWITCH
   ========================================================= */

function setMode(domain) {

  state.domain = domain;

  state.selected = null;

  state.latest = null;

  const copy = MODE_COPY[domain];


  document
    .querySelectorAll(".mode")
    .forEach(b =>
      b.classList.toggle(
        "active",
        b.dataset.domain === domain
      )
    );


  $("eyebrow").textContent = copy.eyebrow;
  $("pageTitle").textContent = copy.title;
  $("pageSub").textContent = copy.sub;
  document.title = copy.title;

  $("mModelsV").textContent = copy.models[0];
  $("mModelsS").textContent = copy.models[1];

  $("scoreLabel").textContent = copy.score;
  $("explLabel").textContent = copy.explanation;

  $("mfgExtras").classList.toggle("hidden", !isMfg());
  $("timelineWrap").classList.toggle("hidden", !isMfg());


  $("emptyState")
    .classList.remove("hidden");

  $("resultState")
    .classList.add("hidden");


  $("decisionBadge").textContent =
    "WAITING";

  $("decisionBadge").className =
    "decision neutral";


  $("recordList").innerHTML = "";

  loadRecords().catch(e => {
    $("recordCount").textContent = "0";
    $("voiceStatus").textContent = e.message;
  });


  if (!state.replaying) {
    $("voiceStatus").textContent = copy.status;
  }

}


/* =========================================================
   RUN SELECTED RECORD
   ========================================================= */

function riskSpan(level) {
  return `<span class="risk-${esc(level)}">${esc(level)}</span>`;
}


function showManufacturingResult(result) {

  const s = result.score;

  const src = result.reasoning_source || "LOCAL_FALLBACK";

  const srcBadge = $("srcBadge");
  srcBadge.textContent = src === "GEMINI" ? "EXPLAINED BY GEMINI" : "LOCAL FALLBACK (Gemini not used)";
  srcBadge.className = "badge " + (src === "GEMINI" ? "ok" : "warn");

  const dataBadge = $("dataBadge");
  dataBadge.textContent = "DATA: " + String(s.data_source || "unknown").replaceAll("_", " ").toUpperCase();
  dataBadge.className = "badge " + (String(s.data_source).startsWith("real") ? "ok" : "warn");

  $("degradedBadge").classList.toggle("hidden", !s.degraded);

  $("mlRisk").innerHTML = riskSpan(s.ml_risk);
  $("sensorRisk").innerHTML = riskSpan(s.sensor_risk);
  $("overallRisk").innerHTML = riskSpan(s.overall_risk);
  $("rulValue").textContent =
    s.rul_cycles !== undefined ? `${s.rul_cycles} cycles` : "n/a";

  $("manualList").innerHTML =
    (result.manual_sections || [])
      .map(t => `<li>${esc(t)}</li>`)
      .join("") || "<li>No manual section matched.</li>";

  const wo = result.work_order;

  $("woBox").innerHTML = wo
    ? `<b>${esc(wo.work_order_id)}</b> · priority ${esc(wo.priority)} · ${esc(String(wo.action).replaceAll("_", " "))}<br>` +
      `Status: ${esc(wo.status)} · ${result.work_order_persisted ? "saved to Firestore" : "not saved (Firestore not configured)"}`
    : "No work order needed (risk is LOW). Continue monitoring.";

  $("agentTrace").innerHTML = "";

}


async function runSelected() {

  if (!state.selected) {
    return;
  }


  $("voiceStatus").textContent =
    "Running all five stages...";


  try {

    const result =
      await getJSON(
        "/api/score",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            domain: state.domain,
            record: state.selected
          })
        }
      );


    state.latest = result;


    const pct =
      Math.round(result.score.score * 100);


    $("scoreValue").textContent =
      pct + "%";


    $("reasonCode").textContent =
      result.score.reason_code;


    $("explanationText").textContent =
      result.explanation;


    if (result.domain === "manufacturing" || result.domain === "sensor") {
      showManufacturingResult(result);
    }


    const badge =
      $("decisionBadge");


    badge.textContent =
      result.action.replaceAll("_", " ").toUpperCase();


    badge.className =
      "decision " + result.action;


    $("emptyState")
      .classList.add("hidden");


    $("resultState")
      .classList.remove("hidden");


    $("voiceStatus").textContent =
      `Assessment complete for ${result.record.id}.`;


    await loadHistory();

  } catch (e) {

    $("voiceStatus").textContent =
      e.message;

  }

}


async function runAgentChain() {

  if (!state.selected || !isMfg()) {
    $("voiceStatus").textContent = "Select a machine first.";
    return;
  }

  const mode = $("agentMode").value;

  $("agentTrace").innerHTML = "<li>Running...</li>";

  try {

    const r = await getJSON("/api/agents/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record: state.selected, mode })
    });

    const m = r.monitor, p = r.prediction, d = r.diagnosis, w = r.work_order;

    $("agentTrace").innerHTML = [
      `<li><b>Sensor Monitor</b>: ${m.anomaly_detected ? esc(m.out_of_band_codes.length) + " sensor(s) out of band" : "all sensors in band"}</li>`,
      `<li><b>Prediction</b>: ${Math.round(p.score * 100)}% failure probability, overall ${esc(p.overall_risk)}</li>`,
      `<li><b>Diagnosis</b>: ${d.reasoning_source === "GEMINI" ? "Gemini" : "local fallback"} using ${esc(d.manual_sections.length)} manual section(s)</li>`,
      `<li><b>Work Order</b>: ${w ? esc(w.work_order_id) + " (" + esc(w.priority) + ")" : "none, risk is LOW"}</li>`,
      `<li class="muted">Orchestrated by ${r.mode === "adk" ? "Google ADK SequentialAgent" : "plain Python"}</li>`
    ].join("");

  } catch (e) {

    $("agentTrace").innerHTML = `<li>${esc(e.message)}</li>`;

  }

}


async function replayStream() {

  if (state.replaying) {
    return;
  }

  const asset = $("replayAsset").value;

  state.replaying = true;

  $("replayBtn").disabled = true;
  $("timeline").innerHTML = "";
  $("timelineNote").textContent = "Loading sensor stream...";

  try {

    const data = await getJSON(`/api/manufacturing/stream?asset=${encodeURIComponent(asset)}&steps=20`);

    const readings = data.readings || [];

    for (let i = 0; i < readings.length; i++) {

      const item = readings[i];

      const bar = document.createElement("div");

      bar.className = "bar " + item.overall_risk;
      bar.style.height = Math.max(6, Math.round(item.score * 100)) + "%";
      bar.title = `reading ${i + 1}: ${Math.round(item.score * 100)}% · ${item.overall_risk}`;

      $("timeline").appendChild(bar);

      $("timelineNote").textContent =
        `Reading ${i + 1} of ${readings.length}: failure probability ${Math.round(item.score * 100)}% (${item.overall_risk}).`;

      $("voiceStatus").textContent =
        `Monitoring ${ASSET_LABELS[asset]}... reading ${i + 1} of ${readings.length}.`;

      await new Promise(res => setTimeout(res, 350));

    }

    if (readings.length) {

      const last = readings[readings.length - 1].record;

      state.selected = last;

      state.replaying = false;

      $("timelineNote").textContent += " Running the full pipeline on the latest reading.";

      await runSelected();

    }

  } catch (e) {

    $("timelineNote").textContent = e.message;

  } finally {

    state.replaying = false;

    $("replayBtn").disabled = false;

  }

}


/* =========================================================
   VOICE / QUESTION ANSWERING
   ========================================================= */

function answerQuestion(qtext) {

  if (!state.latest) {

    $("voiceStatus").textContent =
      "Assess a record first, then ask why it was flagged.";

    return;
  }


  const q =
    qtext.toLowerCase();

  const r =
    state.latest;


  if (
    q.includes("why") ||
    q.includes("reason") ||
    q.includes("flag")
  ) {

    $("explanationText").textContent =
      r.explanation;


    $("voiceStatus").textContent =
      `The main signals were ${
        (r.score.factors || []).join(", ")
        || "the configured risk rules"
      }.`;

    return;
  }


  if (
    (r.domain === "manufacturing" || r.domain === "sensor") &&
    (q.includes("inspect") || q.includes("check") || q.includes("next") || q.includes("do"))
  ) {

    $("voiceStatus").textContent =
      `${r.score.recommendation}. Manual sections used: ${
        (r.manual_sections || []).join("; ") || "none"
      }.`;

    return;
  }


  if (
    (r.domain === "manufacturing" || r.domain === "sensor") &&
    (q.includes("work order") || q.includes("ticket"))
  ) {

    $("voiceStatus").textContent = r.work_order
      ? `Work order ${r.work_order.work_order_id} was created with ${r.work_order.priority} priority.`
      : "No work order was needed because the risk is low.";

    return;
  }


  if (
    q.includes("action") ||
    q.includes("decision") ||
    q.includes("what happens")
  ) {

    const v =
      r.action === "block"
        ? "blocked"
        : r.action === "deny"
          ? "denied"
          : String(r.action).replaceAll("_", " ");


    $("voiceStatus").textContent =
      `The current prototype decision is to ${v} this ${r.domain}.`;

    return;
  }


  if (
    q.includes("score") ||
    q.includes("risk")
  ) {

    $("voiceStatus").textContent =
      (r.domain === "manufacturing" || r.domain === "sensor")
        ? `The estimated failure probability is ${Math.round(r.score.score * 100)}%, and the overall maintenance risk is ${r.score.overall_risk}.`
        : `The estimated risk is ${Math.round(r.score.score * 100)}%.`;

    return;
  }


  $("voiceStatus").textContent =
    "Try asking: why was this flagged, what is the risk score, what should I inspect, or is there a work order?";

}


/* =========================================================
   TEXT TO SPEECH
   ========================================================= */

function speak(t) {

  if (!("speechSynthesis" in window)) {

    $("voiceStatus").textContent =
      "Text-to-speech is not available in this browser.";

    return;
  }


  window.speechSynthesis.cancel();


  window.speechSynthesis.speak(
    new SpeechSynthesisUtterance(t)
  );

}


/* =========================================================
   VOICE INPUT
   ========================================================= */

function startVoiceInput() {

  const Recognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;


  if (!Recognition) {

    $("voiceStatus").textContent =
      "Voice input is not supported in this browser. Type your question instead.";

    return;
  }


  const rec =
    new Recognition();


  rec.lang =
    "en-IN";

  rec.interimResults =
    false;

  rec.maxAlternatives =
    1;


  $("voiceStatus").textContent =
    "Listening...";


  rec.onresult =
    e => {

      const t =
        e.results[0][0].transcript;


      $("question").value =
        t;


      answerQuestion(t);

    };


  rec.onerror =
    () => {

      $("voiceStatus").textContent =
        "Voice input could not be captured. Type your question instead.";

    };


  rec.start();

}


/* =========================================================
   EVENT HANDLERS
   ========================================================= */



document
  .querySelectorAll(".mode")
  .forEach(
    b =>
      b.addEventListener(
        "click",
        () => setMode(b.dataset.domain)
      )
  );


$("askBtn")
  .addEventListener(
    "click",
    () =>
      answerQuestion(
        $("question").value.trim()
      )
  );


$("question")
  .addEventListener(
    "keydown",
    e => {

      if (e.key === "Enter") {

        answerQuestion(
          $("question").value.trim()
        );

      }

    }
  );


$("refreshBtn")
  .addEventListener(
    "click",
    async () => {

      await loadRecords();

      await loadHistory();

    }
  );


$("runAgainBtn")
  .addEventListener(
    "click",
    runSelected
  );


$("speakBtn")
  .addEventListener(
    "click",
    () => {

      if (state.latest) {

        speak(
          state.latest.explanation +
          " Decision: " +
          String(state.latest.action).replaceAll("_", " ") +
          "."
        );

      }

    }
  );


$("micBtn")
  .addEventListener(
    "click",
    startVoiceInput
  );


$("agentsBtn")
  .addEventListener(
    "click",
    runAgentChain
  );


$("replayBtn")
  .addEventListener(
    "click",
    replayStream
  );


/* =========================================================
   INITIALIZE
   ========================================================= */

(async function () {

  try {

    setMode("manufacturing");

    await loadHistory();

  } catch (e) {

    $("voiceStatus").textContent =
      "Unable to initialize demo data: " +
      e.message;

  }

})();
