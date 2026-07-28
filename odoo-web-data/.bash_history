pip install openai
pip install --break-system-packages openai
exit
pip install --break-system-packages anthropic
exit
pip install --break-system-packages google-genai
exit
pip install --break-system-packages openai anthropic google-genai markdown-it-py
exit
pip install --break-system-packages mdit-py-plugins
exit
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page_procedure --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page_work_instruction --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i mgmtsystem_nonconformity --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page_procedure --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page_procedure --stop-after-init
exit
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i management_system,management_system_manual,management_system_audit,management_system_action,management_system_nonconformity,management_system_review,management_system_risk,management_system_objective,document_management_system,base_automation_log,spreadsheet_dashboard,mail_activity_board,project_task_audit_link --stop-after-init
odoo -d odoo_db -i document_page --stop-after-init
odoo -d odoo_db -i document_page_procedure --stop-after-init
odoo -d odoo_db -i document_page_work_instruction --stop-after-init
odoo -d odoo_db --db_user=odoo --db_password=odoo --db_host=db -i document_page_work_instruction --stop-after-init
exit
