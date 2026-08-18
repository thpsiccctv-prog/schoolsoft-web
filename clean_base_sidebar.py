import os

base_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\templates\base.html'
with open(base_path, 'r', encoding='utf-8') as f:
    content = f.read()

finance_clean = '''            {% if access.fee_collection or access.receipts or access.dues or access.collection or access.fee_setup or access.accounts %}
            <div class="nav-section-title">Finance</div>
                {% if access.fee_collection and not is_readonly %}
                <a href="{% url 'core:receipt_create' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M5 3h14v18l-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg></span><span>Fee Collection</span></a>
                {% endif %}
                {% if access.receipts %}
                <a href="{% url 'core:receipt_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 7h4M10 11h4M10 15h3"/></svg></span><span>Receipts</span></a>
                {% endif %}
                {% if access.dues %}
                <a href="{% url 'core:due_up_to_month_report' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg></span><span>Dues up to Month</span></a>
                <a href="{% url 'core:defaulter_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></span><span>Fee Defaulters</span></a>
                {% endif %}
                {% if access.collection %}
                <a href="{% url 'core:collection_report' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg></span><span>Collection</span></a>
                {% endif %}
                {% if access.fee_setup %}
                <a href="{% url 'core:fee_structure_report' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg></span><span>Fee Setup</span></a>
                <a href="{% url 'core:feeder_school_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-4h6v4"/></svg></span><span>Attached Schools (फीडर स्कूल)</span></a>
                {% endif %}
                {% if access.accounts %}
                {% if not is_readonly %}
                <a href="{% url 'core:expense_create' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></span><span>Daily Expense</span></a>
                <a href="{% url 'core:receipt_other_create' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg></span><span>Other Receipt</span></a>
                {% endif %}
                <a href="{% url 'core:voucher_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="14" x2="8.01" y2="14"/><line x1="12" y1="14" x2="12.01" y2="14"/><line x1="16" y1="14" x2="16.01" y2="14"/><line x1="8" y1="18" x2="8.01" y2="18"/><line x1="12" y1="18" x2="12.01" y2="18"/><line x1="16" y1="18" x2="16.01" y2="18"/></svg></span><span>Voucher Register</span></a>
                <a href="{% url 'core:cash_book' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg></span><span>Cash Book</span></a>
                <a href="{% url 'core:ledger_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></span><span>Ledger Master</span></a>
                <a href="{% url 'core:person_list' %}"><span class="nav-icon"><svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></span><span>Persons (Advances)</span></a>
                {% endif %}
            {% endif %}'''

start_marker = '{% if access.fee_collection or access.receipts or access.dues or access.collection or access.fee_setup or access.accounts %}'
end_marker = '{% if access.staff or access.transport or access.inventory or access.family %}'

s_idx = content.find(start_marker)
e_idx = content.find(end_marker)

new_content = content[:s_idx] + finance_clean + "\n\n            " + content[e_idx:]
with open(base_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("base.html Finance section updated successfully!")
