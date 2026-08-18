import csv
import pyodbc
from pathlib import Path

def extract_hindi_names():
    mdb_path = r"E:\THPSIC-INTER-COLLEGE\02-old-data\raw-original\SCHOOL7-COMP35.mdb"
    csv_path = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\HINDI_NAME_MDB_RECOVERY_ATTEMPT.csv")
    report_path = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\HINDI_NAME_RECOVERY_REPORT.md")

    # Connect to the Access database
    conn_str = (
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={mdb_path};"
    )
    
    report_lines = [
        "# Hindi Name MDB Recovery Attempt",
        "",
        "## Summary",
    ]

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("SELECT sid, admno, H_NAME, H_FNAME, H_MNAME FROM ADDMISSION")
        rows = cursor.fetchall()
        
        # Analyze data
        valid_hindi_count = 0
        total_rows = 0
        blank_or_question_count = 0

        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sid", "admno", "H_NAME", "H_FNAME", "H_MNAME"])
            for row in rows:
                total_rows += 1
                sid = row[0]
                admno = row[1]
                h_name = str(row[2]) if row[2] is not None else ""
                h_fname = str(row[3]) if row[3] is not None else ""
                h_mname = str(row[4]) if row[4] is not None else ""

                writer.writerow([sid, admno, h_name, h_fname, h_mname])
                
                # Check validity
                if "?" in h_name or not h_name.strip():
                    blank_or_question_count += 1
                else:
                    valid_hindi_count += 1

        conn.close()

        report_lines.extend([
            f"- Connection successful.",
            f"- Total ADDMISSION rows scanned: {total_rows}",
            f"- Rows with '?' or blank H_NAME: {blank_or_question_count}",
            f"- Rows with potentially valid H_NAME: {valid_hindi_count}",
            "",
            "## Conclusion",
            "If 'Rows with potentially valid H_NAME' is 0 or very low, the Hindi names are unrecoverable from the legacy DB."
        ])

    except Exception as e:
        report_lines.extend([
            "- Connection or Query Failed.",
            f"Error: {e}"
        ])

    with report_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Extraction attempt complete. Report written to {report_path}")

if __name__ == "__main__":
    extract_hindi_names()
