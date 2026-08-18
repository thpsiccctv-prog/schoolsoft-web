import os
import sys

db_path = r"E:\THPSIC SCHOOLSOFT MAIN\SchoolSOFT\34\SCHOOL7.mdb"

print(f"Testing connection to: {db_path}")
print(f"File exists: {os.path.exists(db_path)} (Size: {os.path.getsize(db_path)/(1024*1024):.2f} MB)")

# Try win32com ADODB
try:
    import win32com.client
    conn = win32com.client.Dispatch("ADODB.Connection")
    
    # Try Microsoft.ACE.OLEDB.12.0 or Microsoft.Jet.OLEDB.4.0
    providers = [
        "Provider=Microsoft.ACE.OLEDB.16.0;Data Source={};",
        "Provider=Microsoft.ACE.OLEDB.12.0;Data Source={};",
        "Provider=Microsoft.Jet.OLEDB.4.0;Data Source={};",
    ]
    
    connected = False
    for p in providers:
        conn_str = p.format(db_path)
        try:
            print(f"Trying provider: {p[:30]}...")
            conn.Open(conn_str)
            print(f"SUCCESS with: {p[:35]}")
            connected = True
            break
        except Exception as ex:
            print(f"  Failed: {ex}")
            
    if connected:
        # Get list of tables
        schema = conn.OpenSchema(20) # adSchemaTables
        tables = []
        while not schema.EOF:
            t_name = schema.Fields("TABLE_NAME").Value
            t_type = schema.Fields("TABLE_TYPE").Value
            if t_type == "TABLE":
                tables.append(t_name)
            schema.MoveNext()
        schema.Close()
        print(f"\nTables found ({len(tables)}): {tables}")
        
        # Test query on Fee or StuFee or Manish Kumar
        rs = win32com.client.Dispatch("ADODB.Recordset")
        for tbl in ["FEE", "StuFee", "ADDMISSION", "Student"]:
            if tbl in tables:
                rs.Open(f"SELECT count(*) FROM [{tbl}]", conn)
                cnt = rs.Fields(0).Value
                rs.Close()
                print(f"  Table [{tbl}]: {cnt} rows")
                
        # Check MANISH KUMAR (SID 9087)
        if "StuFee" in tables:
            rs.Open("SELECT * FROM [StuFee] WHERE sid='9087'", conn)
            print("\nStuFee rows for SID 9087 (MANISH KUMAR):")
            while not rs.EOF:
                row_dict = {rs.Fields(i).Name: rs.Fields(i).Value for i in range(rs.Fields.Count)}
                print(" ", row_dict)
                rs.MoveNext()
            rs.Close()
            
        if "FEE" in tables:
            rs.Open("SELECT * FROM [FEE] WHERE SID='9087'", conn)
            print("\nFEE row for SID 9087 (MANISH KUMAR):")
            while not rs.EOF:
                row_dict = {rs.Fields(i).Name: rs.Fields(i).Value for i in range(rs.Fields.Count)}
                print(" ", row_dict)
                rs.MoveNext()
            rs.Close()

        conn.Close()

except Exception as e:
    print(f"Error: {e}")
