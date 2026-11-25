const byId = (id) => document.getElementById(id);
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const endpoint = "/api/transport-requests";
const statusLabels = {
    pending: "Awaiting assignment",
    assigned: "Courier assigned",
    picked_up: "In transit",
    delivered: "Delivered",
    received: "Received",
    cancelled: "Cancelled",
};
const priorityLabels = { critical: "Critical", urgent: "Urgent", standard: "Standard" };
const sampleTypeLabels = JSON.parse(byId("sample-type-labels").textContent);
const priorityRank = { critical: 0, urgent: 1, standard: 2 };
const deadlineRank = (job) => job.due_at ? Date.parse(job.due_at) : Infinity;
const queueOrdering = {
    newest: (jobs) => jobs,
    priority: (jobs) => jobs.sort((a, b) => (priorityRank[a.priority] ?? 2) - (priorityRank[b.priority] ?? 2)),
    deadline: (jobs) => jobs.sort((a, b) => deadlineRank(a) - deadlineRank(b)),
};
const dateFormat = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" });
const requestDialog = byId("request-dialog");
const assignDialog = byId("assign-dialog");
const detailsDialog = byId("details-dialog");
let requests = [];
let visibleRequests = [];
let activeRequestId;
let assignment;
let editing;
let latestRefresh = 0;
let latestDetails = 0;

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function button(text, onClick) {
    const node = element("button", text, "secondary");
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
}

function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value.includes("T") ? value : value.replace(" ", "T") + "Z");
    return Number.isNaN(date.getTime()) ? "—" : dateFormat.format(date);
}

function isOverdue(job) {
    return !["received", "cancelled"].includes(job.status) && job.due_at && Date.parse(job.due_at) < Date.now();
}

function showError(node, message = "") {
    node.textContent = message;
    node.hidden = !message;
}

async function api(path, method = "GET", data) {
    const response = await fetch(path, {
        method,
        cache: "no-store",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: data === undefined ? undefined : JSON.stringify(data),
    });
    if (response.status === 401) {
        window.location.assign("/login");
        throw new Error("Sign in to continue.");
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Request failed. Please try again.");
    return result;
}

function renderSummary() {
    const count = (predicate) => requests.filter(predicate).length;
    byId("total-count").textContent = requests.length;
    byId("transit-count").textContent = count((job) => job.status === "picked_up");
    byId("overdue-count").textContent = count(isOverdue);
    byId("issues-count").textContent = requests.reduce((total, job) => total + (job.open_incidents || 0), 0);
    byId("received-count").textContent = count((job) => job.status === "received");
}

function rowFor(job) {
    const row = document.createElement("tr");
    const sample = element("th");
    sample.scope = "row";
    sample.append(element("strong", job.sample_code), element("span", job.origin + " → " + job.destination, "route"));
    sample.append(element("span", sampleTypeLabels[job.sample_type] || "Unspecified", "route"));
    if (job.open_incidents) {
        sample.append(element("span", job.open_incidents + (job.open_incidents === 1 ? " open issue" : " open issues"), "issue-note"));
    }
    const status = element("span", statusLabels[job.status] || job.status, "status");
    status.dataset.status = job.status;
    const statusCell = element("td");
    statusCell.append(status);
    const priority = element("span", priorityLabels[job.priority] || priorityLabels.standard, "priority");
    priority.dataset.priority = job.priority || "standard";
    const priorityCell = element("td");
    priorityCell.append(priority);
    const deadline = element("td", formatDate(job.due_at));
    if (isOverdue(job)) deadline.append(element("span", "Overdue", "issue-note"));
    const actions = element("td");
    const group = element("div", "", "row-actions");
    if (["pending", "assigned"].includes(job.status)) {
        group.append(button(job.status === "pending" ? "Assign" : "Reassign", () => openAssignment(job)));
        group.append(button("Edit", () => openPlan(job)));
    }
    const view = button("Details", () => openDetails(job));
    view.setAttribute("aria-label", "Details for " + job.sample_code);
    group.append(view);
    actions.append(group);
    const courier = element("td", job.courier_name || "—");
    [statusCell, courier, priorityCell, deadline].forEach((cell, index) => {
        cell.dataset.label = ["Status", "Courier", "Priority", "Deadline"][index];
    });
    row.append(sample, statusCell, courier, priorityCell, deadline, actions);
    return row;
}

function filterRequests() {
    const query = byId("search").value.trim().toLowerCase();
    const status = byId("status-filter").value;
    const priority = byId("priority-filter").value;
    const sampleType = byId("sample-type-filter").value;
    const order = byId("sort").value;
    const matches = requests.filter((job) => {
        const fields = [job.sample_code, job.origin, job.destination, job.courier_name];
        if (query && !fields.some((field) => field && field.toLowerCase().includes(query))) return false;
        if (priority && (job.priority || "standard") !== priority) return false;
        if (sampleType && job.sample_type !== sampleType) return false;
        if (status === "overdue") return isOverdue(job);
        if (status === "issues") return job.open_incidents > 0;
        return !status || job.status === status;
    });
    return queueOrdering[order](matches);
}

function renderQueue() {
    visibleRequests = filterRequests();
    byId("request-rows").replaceChildren(...visibleRequests.map(rowFor));
    byId("queue-table").hidden = !visibleRequests.length;
    byId("empty").hidden = !!visibleRequests.length;
    byId("empty").textContent = requests.length ? "No requests match these filters." : "No requests yet. Create your first transport request.";
    byId("result-count").textContent = visibleRequests.length + " of " + requests.length + " requests";
    byId("export").disabled = !visibleRequests.length;
    document.querySelectorAll("[data-queue-status]").forEach((tile) => {
        tile.setAttribute("aria-pressed", String(tile.dataset.queueStatus === byId("status-filter").value));
    });
}

async function refreshQueue() {
    const refresh = ++latestRefresh;
    byId("refresh").disabled = true;
    showError(byId("queue-error"));
    try {
        const data = await api(endpoint);
        if (refresh !== latestRefresh) return;
        requests = data.requests;
        renderSummary();
        renderQueue();
    } catch (error) {
        if (refresh === latestRefresh) {
            if (!requests.length) byId("result-count").textContent = "Requests unavailable";
            showError(byId("queue-error"), error.message);
        }
    } finally {
        if (refresh === latestRefresh) byId("refresh").disabled = false;
    }
}

function formHandler(form, submit) {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton.disabled) return;
        const error = form.querySelector("[data-error]") || byId("detail-error");
        const closeButton = form.closest("dialog").querySelector("[data-close]");
        showError(error);
        submitButton.disabled = true;
        closeButton.disabled = true;
        try {
            await submit(Object.fromEntries(new FormData(form)));
        } catch (failure) {
            showError(error, failure.message);
        } finally {
            submitButton.disabled = false;
            closeButton.disabled = false;
        }
    });
}

function openAssignment(job) {
    assignment = job;
    byId("assign-form").reset();
    byId("assign-form").elements.courier_name.value = job.courier_name || "";
    showError(byId("assign-form").querySelector("[data-error]"));
    byId("assign-sample").textContent = "Sample " + job.sample_code;
    assignDialog.showModal();
}

function localDateTime(value) {
    const date = new Date(value);
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
}

function openPlan(job = null) {
    editing = job;
    const form = byId("request-form");
    form.reset();
    showError(form.querySelector("[data-error]"));
    byId("request-title").textContent = job ? "Edit transport request" : "New transport request";
    form.querySelector('button[type="submit"]').textContent = job ? "Save changes" : "Create request";
    if (job) {
        for (const field of ["sample_code", "origin", "destination", "sample_type", "priority",
            "container_count", "pickup_contact", "delivery_contact", "instructions"]) {
            form.elements[field].value = job[field] ?? "";
        }
        for (const field of ["pickup_at", "due_at"]) {
            if (job[field]) form.elements[field].value = localDateTime(job[field]);
        }
    }
    requestDialog.showModal();
}

function openDetails(job) {
    activeRequestId = job.id;
    byId("detail-heading").textContent = "Sample " + job.sample_code;
    byId("detail-route").textContent = job.origin + " → " + job.destination;
    if (job.receipt_condition) {
        byId("detail-route").textContent += " · " + (job.receipt_condition === "issue" ? "Received with issue" : "Receipt accepted");
        if (job.receipt_note) byId("detail-route").textContent += " · " + job.receipt_note;
    }
    byId("incident-form").reset();
    byId("cancel-form").reset();
    byId("cancel-form").hidden = !["pending", "assigned"].includes(job.status);
    const facts = [
        ["Containers", String(job.container_count)],
        ["Scheduled pickup", formatDate(job.pickup_at)],
        ["Delivery deadline", formatDate(job.due_at)],
        ["Pickup contact", job.pickup_contact],
        ["Delivery contact", job.delivery_contact],
        ["Handoff instructions", job.instructions],
    ];
    byId("detail-plan").replaceChildren(...facts.filter(([, value]) => value).flatMap(([label, value]) => [
        element("dt", label), element("dd", value),
    ]));
    byId("timeline").replaceChildren();
    byId("incidents").replaceChildren();
    detailsDialog.showModal();
    refreshDetails(job.id);
}

function historyItem(label, actor, date) {
    const node = element("li");
    node.append(element("strong", label), element("span", (actor ? actor + " · " : "") + formatDate(date), "muted"));
    return node;
}

function incidentItem(incident, requestId) {
    const item = element("li");
    item.append(
        element("p", incident.description),
        element("span", "Reported by " + incident.reported_by + " · " + formatDate(incident.reported_at), "muted")
    );
    if (incident.resolved_at) {
        item.append(element("span", "Resolved by " + incident.resolved_by + " · " + formatDate(incident.resolved_at), "resolution"));
    } else {
        const resolve = button("Resolve issue", async () => {
            resolve.disabled = true;
            showError(byId("detail-error"));
            try {
                await api(endpoint + "/" + requestId + "/incidents/" + incident.id + "/resolve", "PATCH");
                await Promise.all([refreshDetails(requestId), refreshQueue()]);
            } catch (error) {
                showError(byId("detail-error"), error.message);
                resolve.disabled = false;
            }
        });
        item.append(resolve);
    }
    return item;
}

async function refreshDetails(requestId) {
    if (requestId !== activeRequestId || !detailsDialog.open) return;
    const refresh = ++latestDetails;
    const feedback = byId("detail-feedback");
    feedback.textContent = "Loading request history…";
    showError(byId("detail-error"));
    try {
        const data = await api(endpoint + "/" + requestId + "/history");
        if (refresh !== latestDetails || !detailsDialog.open) return;
        const job = requests.find((request) => request.id === requestId);
        const history = data.history.map((event) => historyItem(
            event.note ? (statusLabels[event.status] || event.status) + " · " + event.note : statusLabels[event.status] || event.status,
            event.actor, event.changed_at,
        ));
        if (job?.created_at) history.unshift(historyItem("Request created", null, job.created_at));
        byId("timeline").replaceChildren(...(history.length ? history : [element("li", "No status changes yet.")]));
        const issues = data.incidents.map((incident) => incidentItem(incident, requestId));
        byId("incidents").replaceChildren(...(issues.length ? issues : [element("li", "No issues reported.")]));
    } catch (error) {
        if (refresh === latestDetails && detailsDialog.open) showError(byId("detail-error"), error.message);
    } finally {
        if (refresh === latestDetails) feedback.textContent = "";
    }
}

function csvCell(value) {
    const raw = String(value ?? "");
    const safe = /^\s*[=+\-@]|^[\t\r\n]/.test(raw) ? "'" + raw : raw;
    return '"' + safe.replaceAll('"', '""') + '"';
}

function requestsToCsv(jobs) {
    const lines = [["Sample code", "Sample type", "Pickup", "Destination", "Status", "Courier", "Priority", "Deadline (UTC)", "Open issues"]];
    for (const job of jobs) {
        lines.push([job.sample_code, sampleTypeLabels[job.sample_type], job.origin, job.destination, statusLabels[job.status], job.courier_name, job.priority, job.due_at, job.open_incidents]);
    }
    return lines.map((line) => line.map(csvCell).join(",")).join("\r\n");
}

function downloadCsv() {
    const file = new Blob([requestsToCsv(visibleRequests)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(file);
    const link = element("a");
    link.href = url;
    link.download = "bloodtransport-requests.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

for (const dialog of [requestDialog, assignDialog, detailsDialog]) {
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("cancel", (event) => {
        if (dialog.querySelector('button[type="submit"]:disabled')) event.preventDefault();
    });
}
detailsDialog.addEventListener("close", () => { latestDetails += 1; });
byId("new-request").addEventListener("click", () => openPlan());
formHandler(byId("request-form"), async (data) => {
    data.due_at = data.due_at ? new Date(data.due_at).toISOString() : null;
    data.pickup_at = data.pickup_at ? new Date(data.pickup_at).toISOString() : null;
    data.container_count = Number(data.container_count);
    if (editing) {
        await api(endpoint + "/" + editing.id, "PATCH", {...data, revision: editing.revision});
    } else {
        await api(endpoint, "POST", data);
    }
    requestDialog.close();
    await refreshQueue();
});
formHandler(byId("assign-form"), async (data) => {
    await api(endpoint + "/" + assignment.id + "/assign", "POST", {...data, revision: assignment.revision});
    assignDialog.close();
    await refreshQueue();
});
formHandler(byId("cancel-form"), async (data) => {
    const job = requests.find((item) => item.id === activeRequestId);
    await api(endpoint + "/" + job.id + "/cancel", "POST", {...data, revision: job.revision});
    detailsDialog.close();
    await refreshQueue();
});
formHandler(byId("incident-form"), async (data) => {
    const requestId = activeRequestId;
    await api(endpoint + "/" + requestId + "/incidents", "POST", data);
    if (requestId === activeRequestId) byId("incident-form").reset();
    await Promise.all([refreshQueue(), refreshDetails(requestId)]);
});
byId("search").addEventListener("input", renderQueue);
document.querySelectorAll("[data-queue-status]").forEach((tile) => tile.addEventListener("click", () => {
    byId("status-filter").value = tile.dataset.queueStatus;
    renderQueue();
}));
for (const id of ["sample-type-filter", "status-filter", "priority-filter", "sort"]) byId(id).addEventListener("change", renderQueue);
byId("refresh").addEventListener("click", refreshQueue);
byId("export").addEventListener("click", downloadCsv);
refreshQueue();
