(function () {
    function toNumber(value) {
        var parsed = parseFloat(value || "0");
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoney(value) {
        return value.toFixed(2);
    }

    function formatMoneyShort(value) {
        return formatMoney(value).replace(/\.00$/, "");
    }

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>"']/g, function(char) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;"
            }[char];
        });
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
            var detailParts = details ? details.split("|").map(function(part) {
                return part.trim();
            }).filter(Boolean) : [];
            return {
                value: opt.value,
                text: cleanText,
                name: name,
                details: details,
                detailParts: detailParts,
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
                    var detailsHtml = o.detailParts.map(function(part) {
                        return "<span>" + escapeHtml(part) + "</span>";
                    }).join(" ");
                    li.innerHTML = "<strong>" + escapeHtml(o.name) + "</strong> " + badge + "<br><small class='student-result-details'>" + detailsHtml + "</small>";

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
                var detailsHtml = opt.detailParts.map(function(part) {
                    return "<span>" + escapeHtml(part) + "</span>";
                }).join(" ");
                summary.innerHTML = "<strong>" + escapeHtml(opt.name) + "</strong><span class='student-summary-details'>" + detailsHtml + "</span><em>Ready for fee entry</em>";
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
        var paidThrough = document.querySelector("[data-student-paid-through]");
        var nextDue = document.querySelector("[data-student-next-due]");
        var lastPayment = document.querySelector("[data-student-last-payment]");
        var monthStatus = document.querySelector("[data-student-month-status]");
        var fillBalanceButton = document.querySelector("[data-fill-balance-fee]");
        var currentDefaults = null;

        if (!form || !studentSelect) {
            return;
        }

        function selectedTargetMonth() {
            return (toSelect && toSelect.value) || (fromSelect && fromSelect.value) || "MAR";
        }

        function renderMonthStatus(rows) {
            if (!monthStatus) return;
            rows = rows || [];
            monthStatus.innerHTML = rows.map(function(row) {
                var dueAmount = toNumber(row.due_amount);
                var creditAmount = toNumber(row.credit_amount);
                var label = row.month + " Clear";
                var tone = "is-clear";
                if (dueAmount > 0) {
                    label = row.month + " Due " + formatMoneyShort(dueAmount);
                    tone = "is-due";
                } else if (creditAmount > 0) {
                    label = row.month + " Adv " + formatMoneyShort(creditAmount);
                    tone = "is-credit";
                }
                return "<span class='" + tone + "'>" + escapeHtml(label) + "</span>";
            }).join("");
        }

        function resetStatusDetails() {
            if (paidThrough) paidThrough.textContent = "-";
            if (nextDue) nextDue.textContent = "-";
            if (lastPayment) lastPayment.textContent = "-";
            if (monthStatus) monthStatus.innerHTML = "";
        }

        // Track whether a policy concession is currently active for the selected student.
        var policyConcessionActive = false;

        function updateDoubleCountWarning() {
            var warning = document.getElementById('concession-double-count-warning');
            if (!warning) return;
            var concessionInput = document.querySelector("#id_concession_amount");
            var manualAmt = concessionInput ? toNumber(concessionInput.value) : 0;
            warning.style.display = (policyConcessionActive && manualAmt > 0) ? 'block' : 'none';
        }

        // Attach double-count warning listener to the concession input.
        (function () {
            var concessionInput = document.querySelector("#id_concession_amount");
            if (concessionInput) {
                concessionInput.addEventListener("input", updateDoubleCountWarning);
            }
        })();

        function showDueStatus(data) {
            currentDefaults = data;
            var concessionBanner = document.getElementById('concession-banner');
            var concessionType = document.getElementById('concession-type');
            var concessionAmount = document.getElementById('concession-amount');
            var concessionMonthRange = document.getElementById('concession-month-range');
            var concessionReason = document.getElementById('concession-reason');
            var concessionApprovedBy = document.getElementById('concession-approved-by');

            if (data && data.active_concession) {
                var ac = data.active_concession;
                if (concessionType) concessionType.textContent = ac.type;
                if (concessionAmount) concessionAmount.textContent = ac.amount;
                if (concessionMonthRange) concessionMonthRange.textContent = ac.month_range || '';
                if (concessionReason) concessionReason.textContent = ac.reason || '';
                if (concessionApprovedBy) concessionApprovedBy.textContent = ac.approved_by || '';
                if (concessionBanner) concessionBanner.style.display = 'block';
                policyConcessionActive = true;
            } else {
                if (concessionBanner) concessionBanner.style.display = 'none';
                policyConcessionActive = false;
            }
            updateDoubleCountWarning();

            if (!dueCard || !dueValue || !dueNote) return;
            var status = data && data.due_status;
            if (!status) {
                dueCard.hidden = true;
                resetStatusDetails();
                return;
            }
            dueCard.hidden = false;
            dueCard.classList.remove("is-clear", "is-due", "is-credit", "is-warning");
            if (!status.available) {
                dueCard.classList.add("is-warning");
                dueValue.textContent = "-";
                dueNote.textContent = status.error || "Due status not available.";
                resetStatusDetails();
                if (fillBalanceButton) fillBalanceButton.disabled = true;
                return;
            }

            var dueAmount = toNumber(status.due_amount);
            var creditAmount = toNumber(status.credit_amount);
            var paidAmount = toNumber(status.received_amount);
            var demandAmount = toNumber(status.gross_demand);
            if (paidThrough) {
                paidThrough.textContent = (status.last_payment && status.last_payment.month_range) || status.clear_through || "-";
            }
            if (nextDue) nextDue.textContent = status.next_due_month || "No due";
            if (lastPayment) {
                if (status.last_payment) {
                    lastPayment.textContent = status.last_payment.date + " / " + status.last_payment.receipt_no + " / Rs. " + formatMoney(toNumber(status.last_payment.amount));
                } else {
                    lastPayment.textContent = "No receipt in this session";
                }
            }
            renderMonthStatus(status.month_results);
            if (dueAmount > 0) {
                dueCard.classList.add("is-due");
                dueValue.textContent = "Rs. " + formatMoney(dueAmount);
                dueNote.textContent = "Up to " + status.target_month + ": demand Rs. " + formatMoney(demandAmount) + ", paid Rs. " + formatMoney(paidAmount) + ".";
                if (fillBalanceButton) fillBalanceButton.disabled = !data.balance_fee_field;
            } else if (creditAmount > 0) {
                dueCard.classList.add("is-credit");
                dueValue.textContent = "Advance Rs. " + formatMoney(creditAmount);
                dueNote.textContent = "Up to " + status.target_month + ": demand Rs. " + formatMoney(demandAmount) + ", paid Rs. " + formatMoney(paidAmount) + ".";
                if (fillBalanceButton) fillBalanceButton.disabled = true;
            } else {
                dueCard.classList.add("is-clear");
                dueValue.textContent = "Clear";
                dueNote.textContent = "Up to " + status.target_month + ": demand Rs. " + formatMoney(demandAmount) + ", paid Rs. " + formatMoney(paidAmount) + ".";
                if (fillBalanceButton) fillBalanceButton.disabled = true;
            }
        }

        function loadDefaults() {
            var studentId = studentSelect.value;
            if (!studentId) {
                if (dueCard) dueCard.hidden = true;
                resetStatusDetails();
                currentDefaults = null;
                return;
            }

            var url = form.dataset.feeDefaultsUrlTemplate.replace("__student__", studentId);
            var query = [];
            if (sessionSelect && sessionSelect.value) {
                query.push("session=" + encodeURIComponent(sessionSelect.value));
            }
            if (fromSelect && fromSelect.value) {
                query.push("from_month=" + encodeURIComponent(fromSelect.value));
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
                        var identityParts = data.student_identity || [];
                        if (!identityParts.length) {
                            var section = data.section ? "-" + data.section : "";
                            identityParts = ["Class " + (data.class || "") + section];
                        }
                        var identityHtml = identityParts.map(function(part) {
                            return "<span>" + escapeHtml(part) + "</span>";
                        }).join(" ");
                        summary.innerHTML = "<strong>" + escapeHtml(data.student) + "</strong><span class='student-summary-details'>" + identityHtml + "</span><em>Active fee structure loaded</em>";
                    }
                })
                .catch(function () {
                    if (dueCard) {
                        dueCard.hidden = false;
                        dueCard.classList.add("is-warning");
                    }
                    if (dueValue) dueValue.textContent = "-";
                    if (dueNote) dueNote.textContent = "Could not load due status.";
                    resetStatusDetails();
                });
        }

        if (fillBalanceButton) {
            fillBalanceButton.addEventListener("click", function () {
                var status = currentDefaults && currentDefaults.due_status;
                var fieldName = currentDefaults && currentDefaults.balance_fee_field;
                var dueAmount = status && status.available ? toNumber(status.due_amount) : 0;
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
        if (studentSelect.value) {
            loadDefaults();
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
