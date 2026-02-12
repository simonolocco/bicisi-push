import sqlite3

conn = sqlite3.connect('bicisi.db')
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tablas creadas:")
for row in c.fetchall():
    print(f"  - {row[0]}")

# Count records
c.execute("SELECT COUNT(*) FROM categories")
print(f"\nCategorías: {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM admins")
print(f"Admins: {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM settings")
print(f"Settings: {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM reservations")
print(f"Reservaciones: {c.fetchone()[0]}")

# Show categories
print("\nCategorías disponibles:")
c.execute("SELECT name, price_full_day, stock FROM categories")
for row in c.fetchall():
    print(f"  - {row[0]}: ${row[1]}/día, stock: {row[2]}")

# Show admin
print("\nAdmins:")
c.execute("SELECT username FROM admins")
for row in c.fetchall():
    print(f"  - {row[0]}")

conn.close()
print("\n✅ Base de datos SQLite funcionando correctamente!")
