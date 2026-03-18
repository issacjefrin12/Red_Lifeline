# 🩸 Blood Bank Management System - Complete Setup Guide

## Project Structure
```
d:\BBMS\
├── app.py                          # Flask application with all routes
├── schema.sql                       # MySQL database schema (tables, triggers, procedures)
├── requirements.txt                 # Python dependencies
├── README.md                        # Main documentation
├── SETUP_GUIDE.md                   # This file
├── templates/                       # HTML templates
│   ├── base.html                   # Base layout template (Red & White theme)
│   ├── index.html                  # Dashboard (4 cards + summary)
│   ├── add_donor.html              # Form to add new donor
│   ├── view_donors.html            # DataTable with all donors
│   ├── add_hospital.html           # Form to add hospital
│   ├── view_hospitals.html         # DataTable with all hospitals
│   ├── add_donation.html           # Form to record donation
│   ├── view_donations.html         # DataTable with donation history
│   ├── make_request.html           # Form to request blood
│   └── view_requests.html          # DataTable with request management
└── static/                          # CSS/JS assets (Bootstrap 5, DataTables)
```

## 🚀 5-Minute Quick Start

### Prerequisites Check
- [ ] MySQL Server installed and running
- [ ] Python 3.8+ installed
- [ ] Windows/Linux/Mac with terminal access

### Step-by-Step Installation

**1. Open Command Prompt / PowerShell**
```powershell
# Navigate to project
cd d:\BBMS
```

**2. Create Virtual Environment**
```powershell
python -m venv venv
venv\Scripts\activate
```

**3. Install Python Dependencies**
```powershell
pip install -r requirements.txt
```

**4. Create MySQL Database**
```powershell
# Open MySQL in another terminal
.\mysql -u root -p

# Paste this in MySQL:
source d:\BBMS\schema.sql;

# Verify:
SHOW DATABASES;
USE blood_bank_db;
SHOW TABLES;
```

**5. Update Database Credentials in app.py**
Edit line 18-21 in `app.py`:
```python
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'your_password'  # ← CHANGE THIS
app.config['MYSQL_DB'] = 'blood_bank_db'
```

**6. Run the Application**
```powershell
python app.py
```

**7. Open in Browser**
```
http://localhost:5000
```

---

## 📋 Database Schema Summary

### 8 Tables Created:
1. **Donors** - Blood donors (age > 18)
2. **Blood_Inventory** - Stock for 8 blood groups
3. **Hospitals** - Hospital information
4. **Blood_Requests** - Hospital requests
5. **Donations** - Donation records

### 3 Triggers (Automatic Operations):
- Update donor's last donation date
- Increase inventory on donation
- Decrease inventory on request approval

### 3 Stored Procedures:
- `handle_blood_request()` - Auto approve/reject
- `get_inventory_summary()` - Get all inventory
- `get_donor_history()` - Get donor donations

---

## 🎨 Frontend Features

### Dashboard (/)
- **4 Statistics Cards**
  - Total Active Donors
  - Total Units Available
  - Pending Requests
  - Out of Stock Alerts
- Recent donations table
- Blood group inventory overview
- Quick action buttons

### Color Scheme
```
Primary Red:    #e63946
Dark Red:       #d62828
Light Gray:     #f8f9fa
White:          #ffffff
```

### Responsive Design
- Desktop (1200px+)
- Tablet (768px-1199px)
- Mobile (<768px)

---

## 🔄 Core Workflows

### Workflow 1: Donor Adds Blood
```
1. Navigate to Donations → Record Donation
2. Select donor (auto-fills blood group)
3. Enter units (1-10)
4. Select date
5. Submit
6. ✓ Inventory AUTOMATICALLY increases (via trigger)
7. ✓ Donor's last_donation_date AUTOMATICALLY updated
```

### Workflow 2: Hospital Requests Blood
```
1. Navigate to Requests → Make Request
2. Select hospital
3. Choose blood group
4. Enter units
5. Submit
6. ✓ System AUTOMATICALLY checks inventory
   → If sufficient: Auto-approve + deduct inventory
   → If insufficient: Auto-reject
7. View status in Requests page
```

### Workflow 3: Manual Request Management
```
1. Go to Requests → View Requests
2. See all pending requests
3. For each pending request:
   - ✓ Click checkmark to APPROVE (if enough inventory)
   - ✗ Click X to REJECT
4. System automatically adjusts inventory
```

---

## 🔧 Configuration Options

### Change Flask Debug Mode
In `app.py` line 273:
```python
app.run(debug=True)   # Development
app.run(debug=False)  # Production
```

### Change Port Number
In `app.py` line 273:
```python
app.run(port=5000)    # Default
app.run(port=5001)    # Alternative
```

### Change Host
In `app.py` line 273:
```python
app.run(host='0.0.0.0')  # Accept external connections
app.run(host='localhost')  # Local only
```

---

## 🧪 Testing the System

### Test Case 1: Add Donor
```
Name: John Doe
Age: 25
Gender: Male
Blood: O+
Phone: 9876543210
```

### Test Case 2: Add Hospital
```
Name: City Hospital
Contact: 1234567890
Address: 123 Main St, City
Email: hospital@email.com
```

### Test Case 3: Record Donation
```
Select donor: John Doe
Blood Group: O+ (auto-filled)
Units: 2
Date: (select today)
```
→ Check: Blood_Inventory increases by 2 for O+

### Test Case 4: Make Request
```
Hospital: City Hospital
Blood Group: O+
Units: 1
```
→ Check: Auto-approved + Inventory decreases to 1

---

## 🐛 Common Issues & Solutions

### Issue 1: "No module named 'MySQLdb'"
```powershell
pip install flask-mysqldb
pip install MySQLdb-Python
```

### Issue 2: "Can't connect to MySQL server"
```
✓ Check MySQL is running
✓ Check credentials in app.py
✓ Check MySQL port (default 3306)
```

### Issue 3: "Database doesn't exist"
```powershell
# Run schema.sql again:
mysql -u root -p blood_bank_db < d:\BBMS\schema.sql
```

### Issue 4: "Port 5000 already in use"
```
✓ Change port in app.py line 273
OR
✓ Kill process: netstat -ano | findstr :5000
```

### Issue 5: "Templates not found"
```
✓ Ensure templates/ folder exists in d:\BBMS
✓ Check folder spelling (case-sensitive on Linux)
```

---

## 📊 Advanced Usage

### Generate Database Dump
```bash
mysqldump -u root -p blood_bank_db > backup.sql
```

### Import Sample Data
```sql
USE blood_bank_db;

-- Add sample donor
INSERT INTO Donors (name, age, gender, blood_group, phone, status)
VALUES ('John Smith', 30, 'Male', 'O+', '9876543210', 'Active');

-- Add sample hospital
INSERT INTO Hospitals (name, contact, address)
VALUES ('Central Hospital', '1234567890', '123 Main St, City');

-- Add sample donation
INSERT INTO Donations (donor_id, units, donation_date, blood_group)
VALUES (1, 2, '2026-02-13', 'O+');

-- Add sample request
INSERT INTO Blood_Requests (hospital_id, blood_group, units_required)
VALUES (1, 'O+', 1);
```

### View Inventory
```sql
SELECT * FROM Blood_Inventory;
```

### View Request Status
```sql
SELECT br.id, h.name, br.blood_group, br.units_required, br.status
FROM Blood_Requests br
JOIN Hospitals h ON br.hospital_id = h.id;
```

---

## 🔐 Production Checklist

Before deploying to production:
- [ ] Change SECRET_KEY in app.py
- [ ] Set debug=False
- [ ] Update MySQL password
- [ ] Use environment variables for credentials
- [ ] Enable HTTPS
- [ ] Set up backup schedule
- [ ] Configure logging
- [ ] Use production WSGI (Gunicorn)
- [ ] Set up SSL certificates
- [ ] Configure firewall rules

---

## 🚀 Deployment

### Using Gunicorn (Production)
```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Using Docker (Optional)
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

---

## 📱 Mobile Responsive

All pages are mobile-responsive using Bootstrap 5:
- Hamburger menu on mobile
- Stacked tables on small screens
- Touch-friendly buttons
- Optimized form layouts

---

## 🔗 URL Mapping

```
GET  /                      → Dashboard
GET  /donor/add             → Add donor form
POST /donor/add             → Submit donor
GET  /donor/view            → View all donors
GET  /hospital/add          → Add hospital form
POST /hospital/add          → Submit hospital
GET  /hospital/view         → View all hospitals
GET  /donation/add          → Add donation form
POST /donation/add          → Submit donation
GET  /donation/view         → View all donations
GET  /request/make          → Make request form
POST /request/make          → Submit request
GET  /request/view          → View all requests
POST /request/update/<id>   → Update request status (API)
GET  /api/inventory         → Inventory data (JSON)
```

---

## 📈 Performance Tips

1. **Database Indexes**: Schema includes indexes on frequently searched columns
2. **Lazy Loading**: DataTables load records per page
3. **Caching**: Consider Redis for session management
4. **Query Optimization**: Use stored procedures for complex operations
5. **Connection Pooling**: Flask-MySQLdb handles pooling

---

## 🎓 Learning Outcomes

After using this system, you'll understand:
- ✓ Flask web framework
- ✓ MySQL database design
- ✓ Triggers and stored procedures
- ✓ Bootstrap 5 frontend
- ✓ HTML form validation
- ✓ AJAX API calls
- ✓ RESTful API design
- ✓ Responsive web design
- ✓ Database normalization
- ✓ Security best practices

---

## 📚 File Descriptions

### app.py (271 lines)
- Flask application configuration
- 13+ routes for CRUD operations
- Database connection management
- Error handling and validation
- API endpoints for AJAX

### schema.sql (167 lines)
- Database and table creation
- 8 blood group types (O+, O-, A+, A-, B+, B-, AB+, AB-)
- 3 triggers for automation
- 3 stored procedures
- 7 indexes for optimization

### base.html (185 lines)
- Master layout template
- Responsive navbar
- CSS styling (Red & White theme)
- Bootstrap 5 integration
- DataTables JavaScript
- Flash message handling

### index.html (185 lines)
- Dashboard with 4 statistics cards
- Inventory overview table
- Recent donations list
- Quick action buttons
- Real-time timestamp

### Other Templates (9 files)
- Form pages (add_donor, add_hospital, add_donation, make_request)
- Table pages (view_donors, view_hospitals, view_donations, view_requests)
- Client-side validation and AJAX

### requirements.txt
- Flask 2.3.3
- Flask-MySQLdb 1.0.1
- MySQLdb-Python 1.2.5
- MySQL-connector-python 8.0.33

---

## 💡 Tips & Tricks

1. **Quick Dashboard Refresh**: Click the refresh button
2. **DataTables Sorting**: Click column headers to sort
3. **DataTables Search**: Type in the filter box
4. **Blood Group Colors**: 
   - O+ Yellow, O- Yellow
   - A+ Blue, A- Blue
   - B+ Green, B- Green
   - AB+ Red, AB- Red

5. **Batch Operations**: Add multiple records via CSV import (future feature)

---

## 📞 Support Resources

- **Flask Docs**: https://flask.palletsprojects.com/
- **MySQL Docs**: https://dev.mysql.com/doc/
- **Bootstrap 5**: https://getbootstrap.com/
- **DataTables**: https://datatables.net/
- **Python Docs**: https://docs.python.org/3/

---

## ✅ Verification Checklist

After setup, verify:
- [ ] Flask app starts without errors
- [ ] MySQL database created with 5 tables
- [ ] Dashboard loads at localhost:5000
- [ ] Can add a donor
- [ ] Can add a hospital
- [ ] Can record a donation (inventory increases)
- [ ] Can make a request (auto approves if stock available)
- [ ] All tables show DataTables features
- [ ] UI is red and white themed
- [ ] No JavaScript errors in browser console

---

**Version**: 1.0  
**Created**: February 2026  
**Status**: Production Ready ✅

Happy coding! 🩸

---
