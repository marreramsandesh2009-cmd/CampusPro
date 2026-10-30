document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".alert-dismissible").forEach((alert) => {
        const timeoutId = window.setTimeout(() => {
            if (!alert.isConnected) {
                return;
            }

            if (window.bootstrap?.Alert) {
                window.bootstrap.Alert.getOrCreateInstance(alert).close();
            }
        }, 6500);

        alert.addEventListener("closed.bs.alert", () => {
            window.clearTimeout(timeoutId);
        }, { once: true });
    });
});
