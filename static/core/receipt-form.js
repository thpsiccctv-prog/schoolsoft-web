(function () {
    function toNumber(value) {
        var parsed = parseFloat(value || "0");
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoney(value) {
        return value.toFixed(2);
    }

    function setupStudentFilter() {
        var filter = document.querySelector("[data-student-filter]");
        var select = document.querySelector("#id_student");
        if (!filter || !select) {
            return;
        }

        var allOptions = Array.from(select.options).map(function (option) {
            return {
                value: option.value,
                text: option.text,
                selected: option.selected,
            };
        });

        filter.addEventListener("input", function () {
            var query = filter.value.trim().toLowerCase();
            var currentValue = select.value;
            var visibleOptions = allOptions.filter(function (option, index) {
                return index === 0 || !query || option.text.toLowerCase().indexOf(query) !== -1;
            });

            select.innerHTML = "";
            visibleOptions.forEach(function (option) {
                var node = document.createElement("option");
                node.value = option.value;
                node.textContent = option.text;
                node.selected = option.value === currentValue;
                select.appendChild(node);
            });
        });
    }

    function setupTotals() {
        var amountInputs = Array.from(document.querySelectorAll(".amount-input"));
        var concessionInput = document.querySelector("#id_concession_amount");
        var lateFeeInput = document.querySelector("#id_late_fee_amount");
        var receivedInput = document.querySelector("#id_received_amount");
        var feeTotalOutput = document.querySelector("[data-fee-total]");
        var netTotalOutput = document.querySelector("[data-net-total]");
        var dueTotalOutput = document.querySelector("[data-due-total]");

        if (!amountInputs.length || !feeTotalOutput || !netTotalOutput || !dueTotalOutput) {
            return;
        }

        function recalculate() {
            var feeTotal = amountInputs.reduce(function (sum, input) {
                return sum + toNumber(input.value);
            }, 0);
            var concession = toNumber(concessionInput && concessionInput.value);
            var lateFee = toNumber(lateFeeInput && lateFeeInput.value);
            var received = toNumber(receivedInput && receivedInput.value);
            var netTotal = feeTotal + lateFee - concession;
            var dueTotal = Math.max(netTotal - received, 0);

            feeTotalOutput.textContent = formatMoney(feeTotal);
            netTotalOutput.textContent = formatMoney(netTotal);
            dueTotalOutput.textContent = formatMoney(dueTotal);

            if (receivedInput && (!receivedInput.value || receivedInput.value === "0" || receivedInput.value === "0.00")) {
                receivedInput.value = formatMoney(Math.max(netTotal, 0));
                dueTotalOutput.textContent = "0.00";
            }
        }

        amountInputs.concat([concessionInput, lateFeeInput, receivedInput]).forEach(function (input) {
            if (input) {
                input.addEventListener("input", recalculate);
            }
        });
        recalculate();
    }

    function setupFeeDefaults() {
        var form = document.querySelector("[data-fee-defaults-url-template]");
        var studentSelect = document.querySelector("#id_student");
        var sessionSelect = document.querySelector("#id_session");
        if (!form || !studentSelect) {
            return;
        }

        function loadDefaults() {
            var studentId = studentSelect.value;
            if (!studentId) {
                return;
            }

            var url = form.dataset.feeDefaultsUrlTemplate.replace("__student__", studentId);
            if (sessionSelect && sessionSelect.value) {
                url += "?session=" + encodeURIComponent(sessionSelect.value);
            }

            fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}})
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Could not load fee defaults");
                    }
                    return response.json();
                })
                .then(function (data) {
                    Object.keys(data.amounts || {}).forEach(function (fieldName) {
                        var input = document.querySelector("[name='" + fieldName + "']");
                        if (input) {
                            input.value = data.amounts[fieldName];
                            input.dispatchEvent(new Event("input", {bubbles: true}));
                        }
                    });
                })
                .catch(function () {
                    // Keep manual entry usable if defaults are unavailable.
                });
        }

        studentSelect.addEventListener("change", loadDefaults);
        if (sessionSelect) {
            sessionSelect.addEventListener("change", loadDefaults);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setupStudentFilter();
        setupTotals();
        setupFeeDefaults();
    });
})();
