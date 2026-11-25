const id = (name) => document.getElementById(name);
const mode = id("role-board").dataset.mode;
const lab = mode === "laboratory";
const types = JSON.parse(id("role-sample-types").textContent);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const endpoint = "/api/transport-requests";
const dialog = id("role-dialog");
const stages = new Map([
    ["delivered", lab ? "Ready for intake" : "Delivered"],
    ["picked_up", "In transit"],
    ["assigned", "Awaiting pickup"],
    ["pending", "Awaiting assignment"],
    ["received", "Received"],
    ["cancelled", "Cancelled"],
]);
const stageKeys = lab ? ["delivered", "picked_up", "assigned", "pending", "received", "cancelled"]
    : ["assigned", "picked_up", "delivered", "received", "cancelled"];
const priorities = {critical: 0, urgent: 1, standard: 2};
const time = new Intl.DateTimeFormat("en", {dateStyle: "medium", timeStyle: "short"});
let jobs = [];
let selectedId = null;
let busy = false;

function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (className) el.className = className;
    return el;
}

function action(label, callback, className = "secondary") {
    const el = node("button", label, className);
    el.type = "button";
    el.addEventListener("click", callback);
    el.disabled = busy;
    return el;
}

function stamp(timestamp) {
    if (!timestamp) return "—";
    return time.format(new Date(timestamp.includes("T") ? timestamp : timestamp.replace(" ", "T") + "Z"));
}

function showError(el, message = "") {
    el.hidden = !message;
    el.textContent = message;
}

async function api(path, method = "GET", data) {
    const response = await fetch(path, {
        method, cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
        body: data === undefined ? undefined : JSON.stringify(data),
    });
    if (response.status === 401) location.assign("/login");
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Could not complete the request.");
    return result;
}

function renderSummary() {
    id("stage-summary").replaceChildren(...stageKeys.map((stage) => {
        const count = jobs.filter((job) => job.status === stage).length;
        const tile = action("", () => {
            id("role-stage").value = id("role-stage").value === stage ? "" : stage;
            render();
        }, "summary-item stage-tile" + (stage === "delivered" ? " complete" : ""));
        tile.setAttribute("aria-pressed", String(id("role-stage").value === stage));
        tile.append(node("span", stages.get(stage)), node("strong", String(count)));
        return tile;
    }));
}

function renderCard(job) {
    const card = node("article", "", "role-card");
    const heading = node("div", "", "role-card-heading");
    heading.append(node("h3", job.sample_code), node("span", types[job.sample_type] || "Unspecified", "sample-label"));
    const stage = node("span", stages.get(job.status), "status");
    stage.dataset.status = job.status;
    card.append(heading, node("p", job.origin + " → " + job.destination, "muted"), stage);
    const facts = node("dl", "", "role-facts");
    const addFact = (label, value) => facts.append(node("dt", label), node("dd", value));
    addFact("Priority", (job.priority || "standard").replace(/^\w/, (s) => s.toUpperCase()));
    addFact("Deadline", stamp(job.due_at));
    if (job.pickup_at) addFact("Scheduled pickup", stamp(job.pickup_at));
    addFact("Containers", String(job.container_count));
    if (job.due_at && !["received", "cancelled"].includes(job.status) && Date.parse(job.due_at) < Date.now()) {
        addFact("Schedule", "Overdue");
    }
    if (lab) addFact("Courier", job.courier_name || "Unassigned");
    if (job.open_incidents) addFact("Open issues", String(job.open_incidents));
    if (job.receipt_condition) addFact("Receipt", job.receipt_condition === "issue" ? "Received with issue" : "Accepted");
    card.append(facts);
    const actions = node("div", "", "row-actions");
    if (!lab && job.status === "assigned") actions.append(action("Mark as picked up", () => openDetails(job, true), ""));
    if (!lab && job.status === "picked_up") actions.append(action("Mark as delivered", () => openDetails(job, true), ""));
    const view = action(lab && job.status === "delivered" ? "Review intake" : "View details", () => openDetails(job));
    actions.append(view);
    card.append(actions);
    return card;
}

function render() {
    renderSummary();
    const query = id("role-search").value.trim().toLowerCase();
    const stage = id("role-stage").value;
    const type = id("role-type").value;
    const condition = id("role-condition")?.value;
    const priority = id("role-priority")?.value;
    const visible = jobs.filter((job) => (
        (!query || [job.sample_code, job.origin, job.destination].some((value) => value.toLowerCase().includes(query)))
        && (!stage || job.status === stage) && (!type || job.sample_type === type)
        && (!condition || job.receipt_condition === condition) && (!priority || job.priority === priority)
    )).sort((a, b) => (
        stageKeys.indexOf(a.status) - stageKeys.indexOf(b.status)
        || (priorities[a.priority] ?? 2) - (priorities[b.priority] ?? 2)
        || (a.due_at ? Date.parse(a.due_at) : Infinity) - (b.due_at ? Date.parse(b.due_at) : Infinity)
    ));
    id("role-feedback").textContent = visible.length + " of " + jobs.length + (lab ? " samples" : " assignments");
    id("role-cards").replaceChildren(...(visible.length ? visible.map(renderCard) : [
        node("p", jobs.length ? "No records match these filters." : (lab ? "No samples are addressed to your laboratory yet." : "No transports have been assigned to you yet."), "queue-message muted")
    ]));
}

async function refresh() {
    jobs = (await api(endpoint)).requests;
    render();
}

function setBusy(value) {
    busy = value;
    document.querySelectorAll("#role-board button, #role-dialog button").forEach((button) => { button.disabled = value; });
}

async function perform(work, error) {
    if (busy) return;
    setBusy(true);
    showError(error);
    try {
        await work();
    } catch (failure) {
        showError(error, failure.message);
    } finally {
        setBusy(false);
    }
}

async function loadDetails() {
    const job = jobs.find((item) => item.id === selectedId);
    if (!job) return;
    id("role-dialog-title").textContent = "Sample " + job.sample_code;
    const description = [types[job.sample_type], job.origin + " → " + job.destination, stages.get(job.status)];
    if (job.receipt_note) description.push("Receipt note: " + job.receipt_note);
    id("role-dialog-description").textContent = description.filter(Boolean).join(" · ");
    const plan = [
        ["Containers", String(job.container_count)],
        ["Scheduled pickup", stamp(job.pickup_at)],
        ["Delivery deadline", stamp(job.due_at)],
        ["Pickup contact", job.pickup_contact],
        ["Delivery contact", job.delivery_contact],
        ["Handoff instructions", job.instructions],
    ];
    id("role-plan").replaceChildren(...plan.filter(([, value]) => value).flatMap(([label, value]) => [
        node("dt", label), node("dd", value),
    ]));
    if (lab) id("receipt-form").hidden = job.status !== "delivered";
    else {
        id("handoff-form").hidden = !["assigned", "picked_up"].includes(job.status);
        id("handoff-submit").textContent = job.status === "assigned" ? "Confirm pickup" : "Confirm delivery";
    }
    const data = await api(endpoint + "/" + job.id + "/history");
    id("role-history").replaceChildren(...(data.history.length ? data.history.map((event) => {
        const item = node("li");
        item.append(node("strong", stages.get(event.status)), node("span", event.actor + " · " + stamp(event.changed_at), "muted"));
        if (event.note) item.append(node("p", event.note));
        return item;
    }) : [node("li", "No handoffs recorded yet.")]));
    id("role-issues").replaceChildren(...(data.incidents.length ? data.incidents.map((issue) => {
        const item = node("li");
        item.append(node("p", issue.description), node("span", issue.reported_by + " · " + stamp(issue.reported_at), "muted"));
        if (issue.resolved_at) item.append(node("span", "Resolved by " + issue.resolved_by, "resolution"));
        return item;
    }) : [node("li", "No issues reported.")]));
}

function openDetails(job, focusHandoff = false) {
    selectedId = job.id;
    id("role-history").replaceChildren();
    id("role-issues").replaceChildren();
    id("role-issue-form").reset();
    if (lab) id("receipt-form").reset();
    else id("handoff-form").reset();
    dialog.showModal();
    perform(async () => {
        await loadDetails();
        if (focusHandoff) id("handoff-form").elements.note.focus();
    }, id("role-dialog-error"));
}

for (const stage of stageKeys) {
    const option = node("option", stages.get(stage));
    option.value = stage;
    id("role-stage").append(option);
}
id("role-search").addEventListener("input", render);
for (const name of ["role-stage", "role-type", "role-condition", "role-priority"]) id(name)?.addEventListener("change", render);
id("role-refresh").addEventListener("click", () => perform(refresh, id("role-error")));
id("role-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
id("role-issue-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    perform(async () => {
        await api(endpoint + "/" + selectedId + "/incidents", "POST", data);
        form.reset();
        await refresh();
        await loadDetails();
    }, id("role-dialog-error"));
});
if (lab) {
    const form = id("receipt-form");
    form.elements.condition.addEventListener("change", () => {
        form.elements.note.required = form.elements.condition.value === "issue";
    });
    form.addEventListener("reset", () => { form.elements.note.required = false; });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        perform(async () => {
            await api(endpoint + "/" + selectedId + "/receipt", "POST", data);
            form.reset();
            await refresh();
            await loadDetails();
        }, id("role-dialog-error"));
    });
} else {
    const form = id("handoff-form");
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const job = jobs.find((item) => item.id === selectedId);
        const status = job.status === "assigned" ? "picked_up" : "delivered";
        perform(async () => {
            await api(endpoint + "/" + job.id + "/status", "PATCH", {
                status, note: form.elements.note.value, revision: job.revision,
            });
            form.reset();
            await refresh();
            dialog.close();
        }, id("role-dialog-error"));
    });
}
perform(refresh, id("role-error"));
