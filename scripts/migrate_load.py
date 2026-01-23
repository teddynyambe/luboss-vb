"""
Migration script: Load data from MySQL into PostgreSQL staging tables.
"""
import mysql.connector
import psycopg2
from psycopg2.extras import execute_values
from app.core.config import settings
from app.db.base import SessionLocal
from app.models.migration import StgMembers, StgDeposits, StgLoans, StgRepayments, StgPenalties, StgCycles
import os


def load_staging_data():
    """Load data from MySQL into PostgreSQL staging tables."""
    # MySQL connection (configure from env)
    mysql_config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "village_bank")
    }
    
    mysql_conn = mysql.connector.connect(**mysql_config)
    mysql_cursor = mysql_conn.cursor(dictionary=True)
    
    # PostgreSQL connection
    db = SessionLocal()
    
    try:
        # Load users/members
        print("Loading members...")
        mysql_cursor.execute("SELECT * FROM user")
        members = mysql_cursor.fetchall()
        
        for member in members:
            stg_member = StgMembers(
                id=member["id"],
                first_name=member.get("first_name"),
                last_name=member.get("last_name"),
                email=member.get("email")
            )
            db.add(stg_member)
        
        # Load deposits (from transactions)
        print("Loading deposits...")
        mysql_cursor.execute("""
            SELECT * FROM transaction 
            WHERE transaction_type IN ('savings', 'social_fund', 'admin_fee')
        """)
        deposits = mysql_cursor.fetchall()
        
        for deposit in deposits:
            stg_deposit = StgDeposits(
                id=deposit["id"],
                member_id=deposit["member_id"],
                amount=deposit.get("amount"),
                transaction_date=deposit.get("date")
            )
            db.add(stg_deposit)
        
        # Load loans
        print("Loading loans...")
        mysql_cursor.execute("SELECT * FROM loan")
        loans = mysql_cursor.fetchall()
        
        for loan in loans:
            stg_loan = StgLoans(
                id=loan["id"],
                member_id=loan["member_id"],
                loan_amount=loan.get("loan_amount"),
                percentage_interest=loan.get("percentage_interest"),
                application_date=loan.get("application_date"),
                effective_month=loan.get("effective_month"),
                loan_status=loan.get("loan_status")
            )
            db.add(stg_loan)
        
        # Load repayments
        print("Loading repayments...")
        mysql_cursor.execute("""
            SELECT * FROM transaction 
            WHERE transaction_type IN ('loan_repayment', 'interest')
        """)
        repayments = mysql_cursor.fetchall()
        
        for repayment in repayments:
            stg_repayment = StgRepayments(
                id=repayment["id"],
                member_id=repayment["member_id"],
                amount=repayment.get("amount"),
                transaction_date=repayment.get("date")
            )
            db.add(stg_repayment)
        
        # Load penalties
        print("Loading penalties...")
        mysql_cursor.execute("SELECT * FROM penalty_record")
        penalties = mysql_cursor.fetchall()
        
        for penalty in penalties:
            stg_penalty = StgPenalties(
                id=penalty["id"],
                member_id=penalty["member_id"],
                penalty_type_id=penalty["penalty_type_id"],
                date_issued=penalty.get("date_issued"),
                approved=str(penalty.get("approved", 0))
            )
            db.add(stg_penalty)
        
        db.commit()
        print("Staging data loaded successfully")
        
    except Exception as e:
        db.rollback()
        print(f"Error loading staging data: {e}")
        raise
    finally:
        mysql_conn.close()
        db.close()


if __name__ == "__main__":
    load_staging_data()
