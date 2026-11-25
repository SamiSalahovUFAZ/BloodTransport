const planner = document.querySelector("#shift-planner");

if (planner) {
    const data = JSON.parse(document.querySelector("#shift-data").textContent);
    const date = document.querySelector("#shift-date");
    const time = new Intl.DateTimeFormat(document.documentElement.lang, {hour: "numeric", minute: "2-digit"});
    const dateText = new Intl.DateTimeFormat(document.documentElement.lang, {dateStyle: "long"});

    function dayKey(value) {
        return [
            value.getFullYear(),
            String(value.getMonth() + 1).padStart(2, "0"),
            String(value.getDate()).padStart(2, "0"),
        ].join("-");
    }

    function makeRow(job, field) {
        const row = document.createElement("li");
        const link = document.createElement("a");
        link.href = job.url;
        link.textContent = job.code;
        const details = document.createElement("span");
        details.className = "muted";
        const location = field === "pickup" ? job.origin : field === "delivery" ? job.destination : job.origin + " → " + job.destination;
        details.textContent = location + " · " + job.label;
        if (field) {
            const scheduled = document.createElement("time");
            scheduled.dateTime = job[field];
            scheduled.textContent = time.format(new Date(job[field]));
            row.append(scheduled);
        }
        row.append(link, details);
        return row;
    }

    function fillList(list, jobs, field) {
        const rows = jobs.map((job) => makeRow(job, field));
        if (!rows.length) {
            const empty = document.createElement("li");
            empty.textContent = "No requests scheduled.";
            empty.className = "muted";
            rows.push(empty);
        }
        list.replaceChildren(...rows);
    }

    function render() {
        if (!date.value) return;
        const scheduled = (field) => data
            .filter((job) => job.status !== "cancelled" && job[field] && dayKey(new Date(job[field])) === date.value)
            .sort((first, second) => Date.parse(first[field]) - Date.parse(second[field]));
        const pickups = scheduled("pickup");
        const deliveries = scheduled("delivery");
        const unscheduled = data.filter((job) => !["received", "cancelled"].includes(job.status) && !job.pickup && !job.delivery);
        fillList(document.querySelector("#shift-pickups"), pickups, "pickup");
        fillList(document.querySelector("#shift-deliveries"), deliveries, "delivery");
        fillList(document.querySelector("#unscheduled-list"), unscheduled);
        document.querySelector("#shift-summary").textContent = dateText.format(new Date(date.value + "T12:00")) +
            " · " + pickups.length + " pickup(s) · " + deliveries.length + " delivery deadline(s)";
        document.querySelector("#unscheduled-count").textContent = "(" + unscheduled.length + ")";
    }

    function step(amount) {
        const day = date.value ? new Date(date.value + "T12:00") : new Date();
        day.setDate(day.getDate() + amount);
        date.value = dayKey(day);
        render();
    }

    function showToday() {
        date.value = dayKey(new Date());
        render();
    }

    date.addEventListener("change", render);
    document.querySelector("#previous-day").addEventListener("click", () => step(-1));
    document.querySelector("#next-day").addEventListener("click", () => step(1));
    document.querySelector("#shift-today").addEventListener("click", showToday);
    showToday();
}

document.querySelectorAll("[data-print]").forEach((button) => {
    button.addEventListener("click", () => window.print());
});

document.querySelectorAll("[data-resolve]").forEach((button) => {
    button.addEventListener("click", async () => {
        const error = document.querySelector("#tool-error");
        error.hidden = true;
        button.disabled = true;
        try {
            const token = document.querySelector('meta[name="csrf-token"]').content;
            const response = await fetch(button.dataset.resolve, {
                method: "PATCH", headers: {"X-CSRF-Token": token},
            });
            if (!response.ok) {
                const result = await response.json().catch(() => ({}));
                throw new Error(result.error || "Could not resolve the issue.");
            }
            window.location.reload();
        } catch (failure) {
            error.textContent = failure.message;
            error.hidden = false;
            button.disabled = false;
        }
    });
});
