# Blood Bank Management System (BBMS)

A comprehensive, enterprise-grade Blood Bank Management System built with **Python Flask**, **MySQL**, and **Bootstrap 5**. This system provides complete management of blood inventory, donors, hospitals, donations, and blood requests.

## 🩸 Features

### Core Functionality
- **Dashboard**: Real-time statistics with 4 KPI cards
  - Total Active Donors
  - Total Units Available
  - Pending Requests
  - Out of Stock Alerts

- **Donor Management**
  - Add new donors with validation (age > 18)
  - View all active donors with DataTables
  - Track donation history
  - Search and filter capabilities

- **Blood Inventory**
  - Track all 8 blood groups (O+, O-, A+, A-, B+, B-, AB+, AB-)
  - Visual inventory cards
  - Stock level indicators (Low/Adequate/Out of Stock)
  - Automatic inventory updates on donations

- **Hospital Management**
  - Register hospitals requesting blood
  - Store contact information and addresses
  - Email contact support

- **Donation Management**
  - Record blood donations
  - Auto-fill donor blood group
  - Health status tracking
  - Trigger-based inventory updates

- **Blood Request System**
  - Hospitals can request blood
  - Automatic approval/rejection based on inventory
  - Status tracking (Pending/Approved/Rejected)
  - Inventory deduction on approval

- **Professional UI/UX**
  - Red and White professional theme
  - Responsive Bootstrap 5 design
  - Mobile-friendly interface
  - DataTables for advanced filtering/sorting
  - Modals for data entry
  - Real-time notifications

### Database Features
- **Normalized Schema** with 8 tables
- **Triggers** for automatic inventory updates
- **Stored Procedures** for complex operations
- **Indexes** for query optimization
- **Referential Integrity** with foreign keys

## 📋 System Requirements

### Software Requirements
- **Python**: 3.8 or higher
- **MySQL**: 5.7 or higher
- **Browser**: Modern browser (Chrome, Firefox, Safari, Edge)

### Hardware Requirements
- **RAM**: 2GB minimum
- **Storage**: 500MB minimum
- **Processor**: Dual-core 2.0 GHz minimum

## 🚀 Installation & Setup

### Step 1: Prerequisites
Ensure MySQL Server is installed and running on your system.

### Step 2: Clone/Download Project
```bash
# Navigate to project directory
cd d:\BBMS
```

### Step 3: Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Create Database
```bash
# Open MySQL command line
mysql -u root -p

# Then execute the schema file
source d:\BBMS\schema.sql;

# Verify database creation
SHOW DATABASES;
USE blood_bank_db;
SHOW TABLES;
```

### Step 6: Configure Database Connection
Edit `app.py` and update MySQL credentials:
```python
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'your_password'  # Change this
app.config['MYSQL_DB'] = 'blood_bank_db'
```

### Step 7: Run Application
```bash
python app.py
```

The application will start on `http://localhost:5000`

## 📖 Usage Guide

### Dashboard
- View real-time blood inventory status
- Monitor pending requests
- See recent donations
- Access quick action buttons

### Adding a Donor
1. Navigate to **Donors > Add Donor**
2. Fill in all required fields:
   - Full Name
   - Age (must be > 18)
   - Gender
   - Blood Group
   - Phone Number (10-15 digits, unique)
3. Click "Add Donor"

### Recording a Donation
1. Go to **Donations > Record Donation**
2. Select donor (blood group auto-fills)
3. Enter units (1-10, where 1 unit = 500ml)
4. Select donation date
5. Click "Record Donation"
6. **Inventory updates automatically** via trigger

### Making a Blood Request
1. Navigate to **Requests > Make Request**
2. Select hospital
3. Choose blood group
4. Enter units required
5. Click "Submit Request"
6. **Automatic approval/rejection** based on inventory

### Managing Blood Requests
1. Go to **Requests > View Requests**
2. View all pending/approved/rejected requests
3. **For Pending Requests**:
   - Click ✓ to approve (if inventory sufficient)
   - Click ✗ to reject
4. System automatically deducts inventory on approval

### Viewing Inventory
1. Navigate to **Inventory**
2. View all blood groups with:
   - Unit count
   - Stock status
   - Progress bars
3. Color-coded alerts for stock levels

## 📊 Database Schema

### Tables

#### 1. Donors
```
- id (Primary Key)
- name (VARCHAR 100)
- age (INT, Check: > 18)
- gender (ENUM: Male/Female/Other)
- blood_group (ENUM: O+, O-, A+, A-, B+, B-, AB+, AB-)
- phone (VARCHAR 15, UNIQUE)
- last_donation_date (DATE)
- status (ENUM: Active/Inactive)
- created_at (TIMESTAMP)
```

#### 2. Blood_Inventory
```
- blood_group (Primary Key, ENUM)
- quantity_units (INT, DEFAULT 0, Check: >= 0)
- last_updated (TIMESTAMP)
```

#### 3. Hospitals
```
- id (Primary Key)
- name (VARCHAR 150)
- contact (VARCHAR 15)
- address (VARCHAR 255)
- email (VARCHAR 100)
- created_at (TIMESTAMP)
```

#### 4. Blood_Requests
```
- id (Primary Key)
- hospital_id (Foreign Key)
- blood_group (Foreign Key)
- units_required (INT, Check: > 0)
- status (ENUM: Pending/Approved/Rejected)
- request_date (TIMESTAMP)
- approval_date (DATETIME)
```

#### 5. Donations
```
- id (Primary Key)
- donor_id (Foreign Key)
- units (INT, Check: > 0)
- donation_date (DATE)
- blood_group (Foreign Key)
- health_status (VARCHAR 50)
- created_at (TIMESTAMP)
```

### Triggers

#### 1. update_donor_last_donation
Updates `Donors.last_donation_date` when a donation is recorded.

#### 2. increase_inventory_on_donation
Automatically increases `Blood_Inventory.quantity_units` when a donation is added.

#### 3. decrease_inventory_on_approval
Automatically decreases inventory when a request is approved.

### Stored Procedures

#### 1. handle_blood_request
```sql
CALL handle_blood_request(request_id);
```
- Checks inventory against request requirements
- Sets status to 'Approved' if sufficient
- Sets status to 'Rejected' if insufficient

#### 2. get_inventory_summary
```sql
CALL get_inventory_summary();
```
Returns current inventory for all blood groups.

#### 3. get_donor_history
```sql
CALL get_donor_history(donor_id);
```
Returns donation history for a specific donor.

## 🔐 Security Features

- Input validation on all forms
- SQL parameterized queries (preventing SQL injection)
- Password encryption ready (configure as needed)
- CSRF protection via Flask
- Type checking and constraints at database level
- Unique phone numbers for donors
- Status-based access control ready

## 🎨 UI/UX Highlights

- **Color Scheme**: Professional Red (#e63946) and White
- **Responsive**: Works on desktop, tablet, mobile
- **Accessibility**: ARIA labels, semantic HTML
- **Performance**: Optimized CSS/JS, DataTables lazy loading
- **Visual Hierarchy**: Clear typography and spacing
- **Interactive**: Modals, tooltips, progress bars
- **Charts Ready**: Chart.js integration for future analytics

## 🔧 Configuration

### Environment Variables (Optional)
Create a `.env` file for production:
```
FLASK_ENV=production
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DB=blood_bank_db
SECRET_KEY=your-secret-key
```

### Database Backup
```bash
# Backup database
mysqldump -u root -p blood_bank_db > backup.sql

# Restore database
mysql -u root -p blood_bank_db < backup.sql
```

## 📝 API Endpoints

### Web Routes
- `GET /` - Dashboard
- `GET/POST /donor/add` - Add donor
- `GET /donor/view` - View all donors
- `GET/POST /hospital/add` - Add hospital
- `GET /hospital/view` - View all hospitals
- `GET/POST /donation/add` - Record donation
- `GET /donation/view` - View all donations
- `GET/POST /request/make` - Make blood request
- `GET /request/view` - View all requests
- `POST /request/update/<id>` - Update request status

### API Endpoints
- `GET /api/inventory` - Get inventory in JSON format

## 🐛 Troubleshooting

### MySQL Connection Error
```
Error: "No module named 'MySQLdb'"
Solution: pip install flask-mysqldb
```

### Port Already in Use
```bash
# Change port in app.py
app.run(port=5001)
```

### Database Not Found
```bash
# Ensure schema.sql was executed
mysql -u root -p < schema.sql
```

### Template Not Found
```
Ensure templates/ folder is in same directory as app.py
```

## 📚 Future Enhancements

- [ ] User authentication and authorization
- [ ] Email notifications for requests
- [ ] SMS alerts for critical stock levels
- [ ] Analytics and reporting dashboard
- [ ] Batch operations for bulk imports
- [ ] API authentication (OAuth 2.0)
- [ ] Real-time notifications with WebSockets
- [ ] Mobile app (React Native)
- [ ] Payment integration for donations
- [ ] Machine learning for demand prediction

## 📄 License

This project is provided as-is for educational and commercial use.

## 👨‍💼 Support

For issues or questions:
1. Check the troubleshooting section
2. Review database schema for table structure
3. Check Flask documentation: https://flask.palletsprojects.com/
4. MySQL Documentation: https://dev.mysql.com/doc/

## 🎓 Learning Resources

- **Flask**: https://flask.palletsprojects.com/
- **MySQL**: https://dev.mysql.com/doc/
- **Bootstrap 5**: https://getbootstrap.com/docs/5.0/
- **DataTables**: https://datatables.net/
- **SQLAlchemy**: https://www.sqlalchemy.org/

---

**Version**: 1.0  
**Last Updated**: February 13, 2026  
**Developer**: Senior Full-Stack Developer  
**Built with**: Flask + MySQL + Bootstrap 5

---

## Quick Start Commands

```bash
# Complete setup in 5 steps
cd d:\BBMS
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open: **http://localhost:5000**

Enjoy! 🩸
