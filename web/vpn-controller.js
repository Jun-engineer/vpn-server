(() => {
    const CONFIG_KEY = "vpn-controller-config";
    const result = document.getElementById("result");
    const registerResult = document.getElementById("register-result");
    const publicKeyInput = document.getElementById("public-key");
    const apiBase = document.currentScript.dataset.apiBase?.replace(/\/+$/, "");
    let sessionApiKey = "";

    function getApiKey() {
        try {
            const saved = JSON.parse(localStorage.getItem(CONFIG_KEY));
            const savedKey = typeof saved?.apiKey === "string" ? saved.apiKey.trim() : "";
            if (savedKey && saved.apiBase?.replace(/\/+$/, "") === apiBase) {
                return savedKey;
            }
        } catch {
            // Storage can be unavailable or contain an older, invalid entry.
        }

        const apiKey = sessionApiKey || window.prompt("Enter your VPN API key")?.trim();
        if (!apiKey) throw new Error("API key is required.");

        try {
            localStorage.setItem(CONFIG_KEY, JSON.stringify({ apiBase, apiKey }));
        } catch {
            // Keep the key in memory for this page if browser storage is unavailable.
            sessionApiKey = apiKey;
        }
        return apiKey;
    }

    function show(target, message, state = "info") {
        target.textContent = message;
        target.dataset.state = state;
        if (target === registerResult) target.classList.add("visible");
    }

    function describeStatus(response) {
        switch (response.state?.toLowerCase()) {
            case "running": {
                if (response.statusChecksPassed === true) return ["VPN available", "success"];
                const system = response.systemStatus || "initializing";
                const instance = response.instanceStatus || "initializing";
                return [`VPN warming up (system check: ${system}, instance check: ${instance})`, "working"];
            }
            case "pending": return ["VPN starting...", "working"];
            case "stopping": return ["VPN stopping...", "working"];
            case "stopped": return ["VPN not available", "info"];
            default: return [response.message || `Unknown state: ${response.state || "n/a"}`, "info"];
        }
    }

    function describeStart(response) {
        switch (response.state?.toLowerCase()) {
            case "running": return ["Server already running.", "success"];
            case "pending": return ["Starting the server... (Press Check Status to confirm).", "working"];
            default: return [response.message || "Start request sent.", "success"];
        }
    }

    function describeStop(response) {
        switch (response.state?.toLowerCase()) {
            case "stopped": return ["Server already stopped.", "success"];
            case "stopping": return ["Stopping the server... (Press Check Status to confirm).", "working"];
            default: return [response.message || "Stop request sent.", "success"];
        }
    }

    function describeRegistration(response) {
        const ip = response.assignedIp ? `${response.assignedIp}/32` : "unknown";
        const psk = response.presharedKey || "(none)";
        const key = response.publicKey || "(unknown key)";
        const serverKey = response.serverPublicKey || "(unknown server key)";
        const message = response.alreadyExists
            ? `Peer already registered for ${key}. Server key ${serverKey}. Use IP ${ip}. Existing preshared key: ${psk}.`
            : `New peer registered for ${key}. Server key ${serverKey}. Assign IP ${ip} and preshared key ${psk}.`;
        return [message, "success"];
    }

    const describe = {
        start: describeStart,
        stop: describeStop,
        status: describeStatus,
        register: describeRegistration,
    };

    async function callApi(action, body) {
        const target = action === "register" ? registerResult : result;
        try {
            if (!apiBase?.startsWith("https://")) {
                throw new Error("The VPN API URL isn't configured. Check the deployment.");
            }
            const key = getApiKey();
            show(target, "Sending request...", "working");

            const method = action === "status" ? "GET" : "POST";
            const response = await fetch(`${apiBase}/${action}`, {
                method,
                headers: { "Content-Type": "application/json", "x-api-key": key },
                body: method === "POST" ? JSON.stringify(body || { action }) : undefined,
            });

            if (response.status === 403) {
                throw new Error("Access denied. If your API key changed, select Forget saved API key and try again.");
            }

            // The VPN API returns JSON on success. A proxy or gateway error may not.
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error(data?.message || data?.error || `Request failed (${response.status}).`);
            if (!data || typeof data !== "object" || Array.isArray(data)) {
                throw new Error("The VPN API returned an invalid response.");
            }

            show(target, ...describe[action](data));
            return true;
        } catch (error) {
            show(target, error.message || "Request failed.", "error");
            return false;
        }
    }

    document.querySelectorAll("button[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.dataset.action;
            if (action === "stop" && button.dataset.confirmStop !== undefined &&
                !window.confirm("Stop the VPN server? This will disconnect all connected devices.")) {
                return;
            }
            return callApi(action);
        });
    });

    document.getElementById("register-peer")?.addEventListener("click", async () => {
        const publicKey = publicKeyInput.value.trim();
        if (!publicKey) {
            show(registerResult, "Public key is required.", "error");
            return;
        }
        if (await callApi("register", { publicKey })) publicKeyInput.value = "";
    });

    document.getElementById("reset-config").addEventListener("click", () => {
        sessionApiKey = "";
        try {
            localStorage.removeItem(CONFIG_KEY);
        } catch {
            // The in-memory key is cleared even if the browser blocks storage.
        }
        show(result, "Saved API key cleared. Click a button to enter it again.");
    });
})();
