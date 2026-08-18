import os
import pyodbc

mdb_path = r'E:\THPSIC-INTER-COLLEGE\02-old-data\working-copy\SCHOOL7-COMP35-AUDIT-COPY.mdb'
conn_str = rf'Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={mdb_path};'

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Check distinct FR_SCHOOL or LAST_SCH_N values containing CMPS or SAMIM
    print("Checking ADDMISSION table for CMPS / SAMIM:")
    cursor.execute("SELECT DISTINCT FR_SCHOOL FROM ADDMISSION WHERE FR_SCHOOL LIKE '%CMPS%' OR FR_SCHOOL LIKE '%SAMIM%' OR FR_SCHOOL LIKE '%SHAMIM%'")
    rows = cursor.fetchall()
    print("FR_SCHOOL values:", [r[0] for r in rows])
    
    cursor.execute("SELECT DISTINCT LAST_SCH_N FROM ADDMISSION WHERE LAST_SCH_N LIKE '%CMPS%' OR LAST_SCH_N LIKE '%SAMIM%' OR LAST_SCH_N LIKE '%SHAMIM%'")
    rows = cursor.fetchall()
    print("LAST_SCH_N values:", [r[0] for r in rows])
    
    # Let's count students by FR_SCHOOL
    cursor.execute("""
        SELECT FR_SCHOOL, COUNT(*) as cnt 
        FROM ADDMISSION 
        WHERE FR_SCHOOL LIKE '%CMPS%' OR FR_SCHOOL LIKE '%SAMIM%' OR FR_SCHOOL LIKE '%SHAMIM%'
        GROUP BY FR_SCHOOL
    """)
    for r in cursor.fetchall():
        print(f"FR_SCHOOL: '{r[0]}' -> Count: {r[1]}")
        
    # Check tbl_feeder or Sub Group Master in Access DB
    cursor.execute("SELECT * FROM tbl_feeder WHERE Feeder_Name LIKE '%CMPS%' OR Feeder_Name LIKE '%SAMIM%'")
    print("\ntbl_feeder rows:")
    for r in cursor.fetchall():
        print(r)
        
    conn.close()
except Exception as e:
    print("Error:", e)
