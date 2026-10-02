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
  domain: "transaction",
  records: {
    transactions: [],
    loans: []
  },
  selected: null,
  latest: null
};

const $ = id => document.getElementById(id);


async function getJSON(path, options) {
  const r = await fetch(path, options);
  const d = await r.json();

  if (!r.ok) {
    throw new Error(d.error || "Request failed");
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


/* =========================================================
   RECORD LIST
   ========================================================= */

function renderRecords() {

  const list =
    state.domain === "loan"
      ? state.records.loans
      : state.records.transactions;

  $("recordCount").textContent =
    state.records.transactions.length +
    state.records.loans.length;

  $("recordList").innerHTML = list.map(r => {

    const loan = state.domain === "loan";

    const headline = loan
      ? currency(r.loanAmount)
      : currency(r.amount);

    const sub = loan
      ? `${r.employmentType} · LTV ${r.loanToValue}% · credit history ${r.creditHistory ? "positive" : "limited"}`
      : `${r.type} · ${r.location} · origin ${r.nameOrig}`;

    return `
      <article
        class="record ${state.selected?.id === r.id ? "selected" : ""}"
        data-id="${r.id}"
      >

        <div class="record-top">
          <span class="record-id">${r.id}</span>
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

  state.records =
    await getJSON("/api/records");

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

    const label =
      isLoan ? "Loan" : "Transaction";

    const icon =
      isLoan ? "LOAN" : "TXN";

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

          <div class="case-icon ${isLoan ? "loan" : "transaction"}">
            ${icon}
          </div>


          <div class="history-case-copy">

            <div class="history-id">
              ${r.record_id}
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
            ${r.reason_code || ""}
          </span>

        </div>


        <!-- DECISION -->

        <div class="history-decision">

          <span class="decision ${action}">
            ${String(r.action || "").toUpperCase()}
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


  document
    .querySelectorAll(".mode")
    .forEach(b =>
      b.classList.toggle(
        "active",
        b.dataset.domain === domain
      )
    );


  $("emptyState")
    .classList.remove("hidden");

  $("resultState")
    .classList.add("hidden");


  $("decisionBadge").textContent =
    "WAITING";

  $("decisionBadge").className =
    "decision neutral";


  renderRecords();


  $("voiceStatus").textContent =
    domain === "loan"
      ? "Choose a sample loan application to assess default risk."
      : "Choose a sample transaction to assess fraud risk.";

}


/* =========================================================
   RUN SELECTED RECORD
   ========================================================= */

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


    const badge =
      $("decisionBadge");


    badge.textContent =
      result.action.toUpperCase();


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
    q.includes("action") ||
    q.includes("decision") ||
    q.includes("what happens")
  ) {

    const v =
      r.action === "block"
        ? "blocked"
        : r.action === "deny"
          ? "denied"
          : r.action;


    $("voiceStatus").textContent =
      `The current prototype decision is to ${v} this ${r.domain}.`;

    return;
  }


  if (
    q.includes("score") ||
    q.includes("risk")
  ) {

    $("voiceStatus").textContent =
      `The estimated risk is ${
        Math.round(r.score.score * 100)
      }%.`;

    return;
  }


  $("voiceStatus").textContent =
    "Try asking: why was this flagged, what is the risk score, or what is the decision?";

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
          state.latest.action +
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


/* =========================================================
   INITIALIZE
   ========================================================= */

(async function () {

  try {

    await loadRecords();

    await loadHistory();

    $("voiceStatus").textContent =
      "Select a sample transaction to start the demo.";

  } catch (e) {

    $("voiceStatus").textContent =
      "Unable to initialize demo data: " +
      e.message;

  }

})();