(function () {
    function toNumber(value) {
        var parsed = parseFloat(value || "0");
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoney(value) {
        return value.toFixed(2);
    }

    // 1. Custom Dropdown for Student Search
    function setupStudentCustomDropdown() {
        var filterBox = document.querySelector("[data-student-filter]");
        var select = document.querySelector("#id_student");
        var summary = document.querySelector("[data-student-summary]");
        
        if (!filterBox || !select) return;

        select.style.display = "none";

        var dropdown = document.createElement("ul");
        dropdown.className = "student-custom-dropdown";
        dropdown.style.display = "none";
        filterBox.parentNode.appendChild(dropdown);

        var allOptions = Array.from(select.options).map(function(opt) {
            var text = opt.text;
            var isActive = text.indexOf("[INACTIVE]") === -1;
            var cleanText = text.replace("[INACTIVE]", "").trim();
            var name = cleanText;
            var details = "";
            var match = cleanText.match(/^(.*)\s+\((.*)\)$/);
            if (match) {
                name = match[1];
                details = match[2];
            }
            return {
                value: opt.value,
                text: cleanText,
                name: name,
                details: details,
                isActive: isActive,
                selected: opt.selected
            };
        }).filter(o => o.value);

        allOptions.sort(function(a, b) {
            if (a.isActive && !b.isActive) return -1;
            if (!a.isActive && b.isActive) return 1;
            return a.name.localeCompare(b.name);
        });

        var visibleOptions = [];
        var activeIndex = -1;

        function renderDropdown(query) {
            query = (query || "").trim().toLowerCase();
            visibleOptions = allOptions.filter(function(o) {
                return !query || o.text.toLowerCase().indexOf(query) !== -1;
            });

            dropdown.innerHTML = "";
            if (visibleOptions.length === 0) {
                dropdown.innerHTML = "<li class='no-results'>No students found</li>";
            } else {
                visibleOptions.forEach(function(o, index) {
                    var li = document.createElement("li");
                    li.className = "dropdown-item";
                    if (index === activeIndex) li.classList.add("active");
                    
                    var badge = o.isActive ? "" : "<span class='badge inactive'>Inactive/TC</span>";
                    li.innerHTML = "<strong>" + o.name + "</strong> " + badge + "<br><small>" + o.details + "</small>";
                    
                    li.addEventListener("mousedown", function(e) {
                        e.preventDefault();
                        selectStudent(o.value);
                    });
                    dropdown.appendChild(li);
                });
            }
        }

        function selectStudent(value) {
            select.value = value;
            select.dispatchEvent(new Event("change", {bubbles: true}));
            filterBox.value = "";
            dropdown.style.display = "none";
            updateSummary();
        }

        filterBox.addEventListener("focus", function() {
            activeIndex = -1;
            renderDropdown(filterBox.value);
            dropdown.style.display = "block";
        });

        filterBox.addEventListener("blur", function() {
            setTimeout(function() { dropdown.style.display = "none"; }, 150);
        });

        filterBox.addEventListener("input", function() {
            activeIndex = -1;
            renderDropdown(filterBox.value);
            dropdown.style.display = "block";
        });

        filterBox.addEventListener("keydown", function(e) {
            if (dropdown.style.display === "none") return;
            if (e.key === "ArrowDown") {
                e.preventDefault();
                activeIndex = Math.min(activeIndex + 1, visibleOptions.length - 1);
                renderDropdown(filterBox.value);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                activeIndex = Math.max(activeIndex - 1, 0);
                renderDropdown(filterBox.value);
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (activeIndex >= 0 && activeIndex < visibleOptions.length) {
                    selectStudent(visibleOptions[activeIndex].value);
                }
            }
        });

        function updateSummary() {
            if (!summary) return;
            var selectedVal = select.value;
            if (!selectedVal) {
                summary.innerHTML = "<strong>Select a student</strong><span>Fee structure will load automatically after selection.</span>";
                return;
            }
            var opt = allOptions.find(o => o.value === selectedVal);
            if (opt) {
                summary.innerHTML = "<strong>" + opt.name + "</strong><span>" + opt.details + "</span><em>Ready for fee entry</em>";
            }
        }

        select.addEventListener("change", updateSummary);
        updateSummary();
    }

    // 2. Month Chips UI
    function setupMonthChips() {
        var chips = document.querySelectorAll("#month-chips-container button");
        var fromSelect = document.querySelector("#id_from_month");
        var toSelect = document.querySelector("#id_to_month");
        if (!chips.length || !fromSelect || !toSelect) return;

        var months = Array.from(chips).map(btn => btn.dataset.month);
        
        function updateUI() {
            var startIdx = months.indexOf(fromSelect.value);
            var endIdx = months.indexOf(toSelect.value);
            if (startIdx > -1 && endIdx > -1 && startIdx > endIdx) {
                var tmp = startIdx; startIdx = endIdx; endIdx = tmp;
            }

            chips.forEach(function(btn, index) {
                btn.classList.remove("selected", "in-range");
                if (index === startIdx || index === endIdx) {
                    btn.classList.add("selected");
                } else if (startIdx > -1 && endIdx > -1 && index > startIdx && index < endIdx) {
                    btn.classList.add("in-range");
                }
            });
        }

        chips.forEach(function(btn) {
            btn.addEventListener("click", function(e) {
                e.preventDefault();
                var clickedMonth = btn.dataset.month;
                
                if (!fromSelect.value || (fromSelect.value && toSelect.value)) {
                    fromSelect.value = clickedMonth;
                    toSelect.value = "";
                } else {
                    toSelect.value = clickedMonth;
                }
                
                fromSelect.dispatchEvent(new Event("change", {bubbles: true}));
                toSelect.dispatchEvent(new Event("change", {bubbles: true}));
                
                updateUI();
            });
        });

        updateUI();
    }

    // 3. Duplicate Warning Check
    function setupDuplicateCheck() {
        var studentSel = document.querySelector("#id_student");
        var sessionSel = document.querySelector("#id_session");
        var fromSel = document.querySelector("#id_from_month");
        var toSel = document.querySelector("#id_to_month");
        var warnBox = document.querySelector("#duplicate-warning");
        var warnText = document.querySelector("#duplicate-warning-text");

        if (!studentSel || !sessionSel || !fromSel || !toSel || !warnBox) return;

        function check() {
            if (!studentSel.value || !sessionSel.value || !fromSel.value || !toSel.value) {
                warnBox.style.display = "none";
                return;
            }

            var url = "/api/receipts/check-duplicate/?student=" + encodeURIComponent(studentSel.value) + 
                      "&session=" + encodeURIComponent(sessionSel.value) + 
                      "&from_month=" + encodeURIComponent(fromSel.value) + 
                      "&to_month=" + encodeURIComponent(toSel.value);
            
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    if (data.warning) {
                        warnText.textContent = data.message;
                        warnBox.style.display = "block";
                    } else {
                        warnBox.style.display = "none";
                    }
                })
                .catch(e => console.error(e));
        }

        studentSel.addEventListener("change", check);
        sessionSel.addEventListener("change", check);
        fromSel.addEventListener("change", check);
        toSel.addEventListener("change", check);
    }

    function setupTotals() {
        var form = document.querySelector(".classic-fee-form");
        var amountInputs = Array.from(document.querySelectorAll(".amount-input"));
        var lockedLegacyBalance = toNumber(form && form.dataset.lockedLegacyBalance);
        var concessionInput = document.querySelector("#id_concession_amount");
        var lateFeeInput = document.querySelector("#id_late_fee_amount");
        var receivedInput = document.querySelector("#id_received_amount");
        var feeTotalOutput = document.querySelector("[data-fee-total]");
        var netTotalOutput = document.querySelector("[data-net-total]");
        var dueTotalOutput = document.querySelector("[data-due-total]");

        if (!amountInputs.length || !feeTotalOutput || !netTotalOutput || !dueTotalOutput) {
            return;
        }

        var dueRow = dueTotalOutput.closest(".pay-total-row");

        function recalculate() {
            var feeTotal = amountInputs.reduce(function (sum, input) {
                return sum + toNumber(input.value);
            }, 0);
            var concession = toNumber(concessionInput && concessionInput.value);
            var lateFee = toNumber(lateFeeInput && lateFeeInput.value);
            var received = toNumber(receivedInput && receivedInput.value);
            var netTotal = feeTotal + lockedLegacyBalance + lateFee - concession;
            var rawDue = netTotal - received;

            feeTotalOutput.textContent = formatMoney(feeTotal);
            netTotalOutput.textContent = formatMoney(netTotal);
            dueTotalOutput.textContent = formatMoney(rawDue);
            if (dueRow) {
                dueRow.classList.toggle("is-advance", rawDue < 0);
            }

            if (receivedInput && (!receivedInput.value || receivedInput.value === "0" || receivedInput.value === "0.00")) {
                receivedInput.value = formatMoney(Math.max(netTotal, 0));
                dueTotalOutput.textContent = "0.00";
                if (dueRow) {
                    dueRow.classList.remove("is-advance");
                }
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
        var fromSelect = document.querySelector("#id_from_month");
        var toSelect = document.querySelector("#id_to_month");
        var receivedInput = document.querySelector("#id_received_amount");
        var concessionInput = document.querySelector("#id_concession_amount");
        var lateFeeInput = document.querySelector("#id_late_fee_amount");
        var dueCard = document.querySelector("[data-student-due-card]");
        var dueValue = document.querySelector("[data-student-current-due]");
        var dueNote = document.querySelector("[data-student-due-note]");
        var fillBalanceButton = document.querySelector("[data-fill-balance-fee]");
        var currentDefaults = null;

        if (!form || !studentSelect) {
            return;
        }

        function selectedTargetMonth() {
            return (toSelect && toSelect.value) || (fromSelect && fromSelect.value) || "MAR";
        }

        function showDueStatus(data) {
            currentDefaults = data;
            if (!dueCard || !dueValue || !dueNote) return;
            var status = data && data.due_status;
            if (!status) {
                dueCard.hidden = true;
                return;
            }
            dueCard.hidden = false;
            dueCard.classList.remove("is-clear", "is-due", "is-credit", "is-warning");
            if (!status.available) {
                dueCard.classList.add("is-warning");
                dueValue.textContent = "-";
                dueNote.textContent = status.error || "Due status not available.";
                if (fillBalanceButton) fillBalanceButton.disabled = true;
                return;
            }

            var receiptBalance = data.receipt_balance_due;
            var receiptBalanceAmount = receiptBalance ? toNumber(receiptBalance.amount) : 0;
            var dueAmount = toNumber(status.due_amount);
            var creditAmount = toNumber(status.credit_amount);
            if (receiptBalanceAmount > 0) {
                dueCard.classList.add("is-due");
                dueValue.textContent = "Rs. " + formatMoney(receiptBalanceAmount);
                dueNote.textContent = "Receipt balance from " + receiptBalance.receipt_no + " (" + receiptBalance.receipt_date + ") will be used first. New setup due up to " + status.target_month + ": Rs. " + formatMoney(dueAmount) + ".";
                if (fillBalanceButton) fillBalanceButton.disabled = !data.balance_fee_field;
            } else if (dueAmount > 0) {
                dueCard.classList.add("is-due");
                dueValue.textContent = "Rs. " + formatMoney(dueAmount);
                dueNote.textContent = "Up to " + status.target_month + ": demand Rs. " + formatMoney(toNumber(status.gross_demand)) + ", paid Rs. " + formatMoney(toNumber(status.received_amount)) + ".";
                if (fillBalanceButton) fillBalanceButton.disabled = !data.balance_fee_field;
            } else if (creditAmount > 0) {
                dueCard.classList.add("is-credit");
                dueValue.textContent = "Advance Rs. " + formatMoney(creditAmount);
                dueNote.textContent = "Up to " + status.target_month + " no due. Advance/credit available.";
                if (fillBalanceButton) fillBalanceButton.disabled = true;
            } else {
                dueCard.classList.add("is-clear");
                dueValue.textContent = "Clear";
                dueNote.textContent = "Up to " + status.target_month + " no due.";
                if (fillBalanceButton) fillBalanceButton.disabled = true;
            }
        }

        function loadDefaults() {
            var studentId = studentSelect.value;
            if (!studentId) {
                if (dueCard) dueCard.hidden = true;
                currentDefaults = null;
                return;
            }

            var url = form.dataset.feeDefaultsUrlTemplate.replace("__student__", studentId);
            var query = [];
            if (sessionSelect && sessionSelect.value) {
                query.push("session=" + encodeURIComponent(sessionSelect.value));
            }
            query.push("month=" + encodeURIComponent(selectedTargetMonth()));
            url += "?" + query.join("&");

            fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}})
                .then(function (response) {
                    if (!response.ok) throw new Error("Could not load fee defaults");
                    return response.json();
                })
                .then(function (data) {
                    var amountInputs = Array.from(document.querySelectorAll(".amount-input"));
                    amountInputs.forEach(function (input) {
                        input.value = "0.00";
                    });
                    Object.keys(data.amounts || {}).forEach(function (fieldName) {
                        var input = document.querySelector("[name='" + fieldName + "']");
                        if (input) {
                            input.value = data.amounts[fieldName];
                        }
                    });
                    amountInputs.forEach(function (input) {
                        input.dispatchEvent(new Event("input", {bubbles: true}));
                    });
                    showDueStatus(data);

                    var summary = document.querySelector("[data-student-summary]");
                    if (summary && data.student) {
                        var section = data.section ? "-" + data.section : "";
                        summary.innerHTML = "<strong>" + data.student + "</strong><span>Class " + (data.class || "") + section + "</span><em>Active fee structure loaded</em>";
                    }
                })
                .catch(function () {
                    if (dueCard) {
                        dueCard.hidden = false;
                        dueCard.classList.add("is-warning");
                    }
                    if (dueValue) dueValue.textContent = "-";
                    if (dueNote) dueNote.textContent = "Could not load due status.";
                });
        }

        if (fillBalanceButton) {
            fillBalanceButton.addEventListener("click", function () {
                var status = currentDefaults && currentDefaults.due_status;
                var fieldName = currentDefaults && currentDefaults.balance_fee_field;
                var receiptBalance = currentDefaults && currentDefaults.receipt_balance_due;
                var receiptBalanceAmount = receiptBalance ? toNumber(receiptBalance.amount) : 0;
                var dueAmount = receiptBalanceAmount > 0 ? receiptBalanceAmount : (status && status.available ? toNumber(status.due_amount) : 0);
                if (!fieldName || dueAmount <= 0) return;

                var amountInputs = Array.from(document.querySelectorAll(".amount-input"));
                amountInputs.forEach(function (input) {
                    input.value = "0.00";
                });
                var balanceInput = document.querySelector("[name='" + fieldName + "']");
                if (balanceInput) {
                    balanceInput.value = formatMoney(dueAmount);
                }
                if (concessionInput) concessionInput.value = "0.00";
                if (lateFeeInput) lateFeeInput.value = "0.00";
                if (receivedInput) receivedInput.value = formatMoney(dueAmount);
                amountInputs.forEach(function (input) {
                    input.dispatchEvent(new Event("input", {bubbles: true}));
                });
                if (receivedInput) {
                    receivedInput.dispatchEvent(new Event("input", {bubbles: true}));
                    receivedInput.focus();
                    receivedInput.select();
                }
            });
        }

        studentSelect.addEventListener("change", loadDefaults);
        if (sessionSelect) {
            sessionSelect.addEventListener("change", loadDefaults);
        }
        if (fromSelect) {
            fromSelect.addEventListener("change", loadDefaults);
        }
        if (toSelect) {
            toSelect.addEventListener("change", loadDefaults);
        }
    }
    document.addEventListener("DOMContentLoaded", function () {
        setupStudentCustomDropdown();
        setupMonthChips();
        setupDuplicateCheck();
        setupTotals();
        setupFeeDefaults();
    });
})();
