import streamlit as st
import pandas as pd
import openpyxl
from datetime import datetime
import hashlib
import random

# Page configuration
st.set_page_config(
    page_title="Club Task Management System",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Helper Functions ---
def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    """Verify password against hash"""
    return hash_password(password) == hashed

def update_tasks_sheet(df):
    """Update only the Tasks sheet while preserving other sheets"""
    try:
        # If file doesn't exist, create it with just the Tasks sheet
        try:
            book = openpyxl.load_workbook("club_tasks.xlsx")
        except FileNotFoundError:
            book = None
        with pd.ExcelWriter("club_tasks.xlsx", engine="openpyxl", mode="a" if book else "w", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name="Tasks", index=False)
        return True
    except Exception as e:
        st.error(f"Error updating tasks: {str(e)}")
        return False

def load_data():
    """Load Excel data with error handling and initialize if missing"""
    members_cols = ["Name", "Role", "Password"]
    tasks_cols = ["TaskID", "TaskName", "AssignedTo", "Role", "Status", "Deadline", "Priority", "Description"]
    try:
        tasks_df = pd.read_excel("club_tasks.xlsx", sheet_name="Tasks")
    except Exception:
        tasks_df = pd.DataFrame(columns=tasks_cols)
    try:
        members_df = pd.read_excel("club_tasks.xlsx", sheet_name="Members")
    except Exception:
        members_df = pd.DataFrame(columns=members_cols)
    # Clean column names
    tasks_df.columns = tasks_df.columns.str.strip()
    members_df.columns = members_df.columns.str.strip()
    return tasks_df, members_df

def get_subordinates(member_name, members_df):
    """Get list of subordinates for a given member based on hierarchy and domain."""
    if members_df.empty:
        return []

    try:
        member_row = members_df[members_df["Name"] == member_name]
        if member_row.empty:
            return []
        member_role = member_row["Role"].iloc[0]

        # Core Head: assign to Domain Heads and other Core Heads
        if member_role == "Core Head":
            allowed_roles = ["Domain Head", "Core Head"]
            return members_df[members_df["Role"].isin(allowed_roles)]["Name"].tolist()

        # Domain Head: assign to Associate Heads in their domain
        elif member_role == "Domain Head":
            # Find domain (assume domain is in another column, e.g., "Domain")
            if "Domain" in members_df.columns:
                domain = member_row["Domain"].iloc[0]
                return members_df[
                    (members_df["Role"] == "Associate Head") & (members_df["Domain"] == domain)
                ]["Name"].tolist()
            else:
                return members_df[members_df["Role"] == "Associate Head"]["Name"].tolist()

        # Associate Head: assign to Junior Heads under them
        elif member_role == "Associate Head":
            # If you have a "ReportsTo" or "Parent" column, use it for strict mapping
            if "ReportsTo" in members_df.columns:
                return members_df[
                    (members_df["Role"] == "Junior Head") & (members_df["ReportsTo"] == member_name)
                ]["Name"].tolist()
            else:
                return members_df[members_df["Role"] == "Junior Head"]["Name"].tolist()

        # Junior Head: no subordinates
        else:
            return []
    except Exception as e:
        return []

def authenticate_user(username, password, members_df):
    """Authenticate user credentials robustly"""
    if members_df.empty:
        return False, None, None

    user_row = members_df[members_df["Name"] == username]
    if user_row.empty:
        return False, None, None

    if "Password" in members_df.columns:
        stored_password = str(user_row["Password"].iloc[0])
        # If the stored password looks like a hash (64 hex chars), compare hashes
        if len(stored_password) == 64 and all(c in "0123456789abcdef" for c in stored_password.lower()):
            if hash_password(password) == stored_password:
                return True, username, user_row["Role"].iloc[0]
        else:
            # Otherwise, compare as plain text
            if password == stored_password:
                return True, username, user_row["Role"].iloc[0]
    else:
        # No password column: default password is "password123"
        if password == "password123":
            return True, username, user_row["Role"].iloc[0]

    return False, None, None

def register_user(name, password, role, members_df):
    """Register a new user and add to Members sheet and Tasks sheet"""
    hashed_pw = hash_password(password)
    new_user = {
        "Name": name,
        "Role": role,
        "Password": hashed_pw
    }
    if members_df.empty:
        members_df = pd.DataFrame([new_user])
    else:
        if name in members_df["Name"].values:
            return False, "User already exists."
        members_df = pd.concat([members_df, pd.DataFrame([new_user])], ignore_index=True)
    # Ensure Tasks sheet exists and has columns
    try:
        tasks_df = pd.read_excel("club_tasks.xlsx", sheet_name="Tasks")
    except Exception:
        tasks_df = pd.DataFrame(columns=["TaskID", "TaskName", "AssignedTo", "Role", "Status", "Deadline", "Priority", "Description"])
    # Add placeholder row for new user
    new_task = {col: "-" for col in tasks_df.columns}
    if "AssignedTo" in tasks_df.columns:
        new_task["AssignedTo"] = name
    if "Role" in tasks_df.columns:
        new_task["Role"] = role
    if "TaskID" in tasks_df.columns:
        new_task["TaskID"] = generate_unique_taskid(tasks_df)
    tasks_df = pd.concat([tasks_df, pd.DataFrame([new_task])], ignore_index=True)
    # Save both sheets
    try:
        with pd.ExcelWriter("club_tasks.xlsx", engine="openpyxl", mode="w") as writer:
            tasks_df.to_excel(writer, sheet_name="Tasks", index=False)
            members_df.to_excel(writer, sheet_name="Members", index=False)
        return True, "Registration successful! You can now log in."
    except Exception as e:
        return False, f"Error saving user: {str(e)}"

def generate_unique_taskid(tasks_df):
    """Generate a unique random TaskID not already in use."""
    if tasks_df.empty or "TaskID" not in tasks_df.columns:
        return random.randint(100000, 999999)
    existing_ids = set(pd.to_numeric(tasks_df["TaskID"], errors="coerce").dropna().astype(int))
    while True:
        new_id = random.randint(100000, 999999)
        if new_id not in existing_ids:
            return new_id

# --- Session State Initialization ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "page" not in st.session_state:
    st.session_state.page = "login"

# --- Authentication Page ---
def show_login_page():
    st.title("🔐 Club Task Management - Login")
    st.markdown("---")
    _, members_df = load_data()
    if members_df.empty:
        st.warning("No users found. Please register the first user.")
        if st.button("Register as First User"):
            st.session_state.page = "register"
            st.rerun()
        return
    
    # Load members data
    _, members_df = load_data()
    
    if members_df.empty:
        st.error("Cannot load member d  ata. Please check your Excel file.")
        return
    
    # Login form
    with st.form("login_form"):
        st.subheader("Sign In")
        username = st.selectbox("Select Your Name", [""] + members_df["Name"].tolist())
        password = st.text_input("Password", type="password", help="Default password: password123")
        submit_button = st.form_submit_button("Sign In")
        
        if submit_button:
            if username and password:
                success, user, role = authenticate_user(username, password, members_df)
                if success:
                    st.session_state.authenticated = True
                    st.session_state.user_name = user
                    st.session_state.user_role = role
                    st.session_state.page = "dashboard"
                    st.success(f"Welcome {user}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please try again.")
            else:
                st.warning("Please enter both username and password.")
    
    st.markdown("Don't have an account? [Register here](#)", unsafe_allow_html=True)
    if st.button("Register as New User"):
        st.session_state.page = "register"
        st.rerun()

    # Help section
    with st.expander("ℹ️ Help & Information"):
        st.info("""
        **Default Login Information:**
        - Password for all users: `password123`
        - Select your name from the dropdown
        
        **Role Hierarchy:**
        - **Core**: Can see all tasks, assign to anyone, delete tasks
        - **Domain Head**: Can assign to Associates and Junior Heads
        - **Associate**: Can assign to Junior Heads
        - **Junior Head**: Can only update their own task status
        """)

# --- Registration Page ---
def show_register_page():
    st.title("📝 Register New User")
    st.markdown("---")
    _, members_df = load_data()
    if members_df.empty:
        st.info("Registering the first user. It's recommended to choose 'Core Head' for admin access.")
        role_options = ["Core Head", "Domain Head", "Associate Head", "Junior Head"]
    else:
        role_options = ["Junior Head", "Associate Head", "Domain Head", "Core Head"]
    
    with st.form("register_form"):
        name = st.text_input("Your Name")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        role = st.selectbox("Role", role_options)
        submit = st.form_submit_button("Register")

        if submit:
            if not name or not password or not confirm_password:
                st.warning("Please fill all fields.")
            elif password != confirm_password:
                st.warning("Passwords do not match.")
            else:
                success, msg = register_user(name, password, role, members_df)
                if success:
                    st.success(msg)
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error(msg)

    # Add Back to Login button
    if st.button("⬅️ Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# --- Dashboard Page ---
def show_dashboard():
    tasks_df, members_df = load_data()

    if tasks_df.empty or members_df.empty:
        st.error("Cannot load data. Please check your Excel file.")
        return

    # Header with logout
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"📌 Welcome, {st.session_state.user_name}")
        st.subheader(f"Role: {st.session_state.user_role}")
    with col2:
        if st.button("🔓 Logout"):
            st.session_state.authenticated = False
            st.session_state.user_name = None
            st.session_state.user_role = None
            st.session_state.page = "login"
            st.rerun()

    st.markdown("---")

    # Filter tasks based on role and user
    user_name = st.session_state.user_name
    user_role = st.session_state.user_role

    if user_role == "Core Head":
        # See all tasks assigned to Core and Domain Heads
        allowed_roles = ["Core Head", "Domain Head"]
        view_df = tasks_df[tasks_df["Role"].isin(allowed_roles)].copy()
        st.info("🔥 Core Head: You can see and assign tasks to Core and Domain Heads.")
    elif user_role == "Domain Head":
        # See tasks assigned to self and to Associate Heads in their domain
        subordinates = get_subordinates(user_name, members_df)
        view_df = tasks_df[
            (tasks_df["AssignedTo"] == user_name) |
            (tasks_df["AssignedTo"].isin(subordinates))
        ].copy()
        st.info("👑 Domain Head: You can see and assign tasks to Associate Heads in your domain.")
    elif user_role == "Associate Head":
        # See tasks assigned to self and to Junior Heads under them
        subordinates = get_subordinates(user_name, members_df)
        view_df = tasks_df[
            (tasks_df["AssignedTo"] == user_name) |
            (tasks_df["AssignedTo"].isin(subordinates))
        ].copy()
        st.info("⭐ Associate Head: You can see and assign tasks to your Junior Heads.")
    else:  # Junior Head
        # Only see tasks assigned to self
        view_df = tasks_df[tasks_df["AssignedTo"] == user_name].copy()
        st.info("📝 Junior Head: You can only see and update your own tasks.")
    
    # Task Summary
    if not view_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📋 Total Tasks", len(view_df))
        with col2:
            st.metric("✅ Completed", (view_df["Status"] == "Done").sum())
        with col3:
            st.metric("⏳ In Progress", (view_df["Status"] == "In Progress").sum())
        with col4:
            st.metric("🔴 Not Started", (view_df["Status"] == "Not Started").sum())
    
    # Main content in tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 My Tasks", "➕ Add Task", "🔄 Update Status", "🗑️ Delete Task"])
    
    with tab1:
        st.subheader("📋 Task List")
        if not view_df.empty:
            # Color-code tasks by status
            def color_status(val):
                if val == "Done":
                    return "background-color: #56f57c"
                elif val == "In Progress":
                    return "background-color: #ffd347"
                else:
                    return "background-color: #f5626f"
            
            styled_df = view_df.style.applymap(color_status, subset=['Status'])
            st.write(styled_df)  # <-- Use this instead of st.dataframe
            
            # Task details
            if st.checkbox("Show Task Details"):
                selected_task = st.selectbox("Select Task for Details", view_df["TaskID"].tolist())
                task_details = view_df[view_df["TaskID"] == selected_task].iloc[0]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.info(f"**Task Name:** {task_details['TaskName']}")
                    st.info(f"**Assigned To:** {task_details['AssignedTo']}")
                    st.info(f"**Role:** {task_details['Role']}")
                with col2:
                    st.info(f"**Status:** {task_details['Status']}")
                    st.info(f"**Priority:** {task_details['Priority']}")
                    st.info(f"**Deadline:** {task_details['Deadline']}")
        else:
            st.info("No tasks to display.")
    
    with tab2:
        st.subheader("✏️ Add New Task")
        can_assign = False
        if user_role == "Core Head":
            can_assign = True
            subordinates = get_subordinates(user_name, members_df)
        elif user_role == "Domain Head":
            can_assign = True
            subordinates = get_subordinates(user_name, members_df)
        elif user_role == "Associate Head":
            can_assign = True
            subordinates = get_subordinates(user_name, members_df)
        else:
            subordinates = []
        
        if can_assign and subordinates:
            with st.form("add_task_form"):
                new_task_name = st.text_input("Task Name*")
                new_assignee = st.selectbox("Assign To*", subordinates)
                new_priority = st.selectbox("Priority", ["High", "Medium", "Low"])
                new_deadline = st.date_input("Deadline", value=datetime.now().date())
                task_description = st.text_area("Task Description (Optional)")
                
                submit_task = st.form_submit_button("➕ Add Task")
                
                if submit_task:
                    if new_task_name.strip():
                        # Get assignee role
                        assignee_role = members_df[members_df["Name"] == new_assignee]["Role"].iloc[0]
                        
                        # Create new task
                        new_task_id = generate_unique_taskid(tasks_df)
                        new_task_data = {
                            "TaskID": new_task_id,
                            "TaskName": new_task_name,
                            "AssignedTo": new_assignee,
                            "Role": assignee_role,
                            "Status": "Not Started",
                            "Deadline": new_deadline,
                            "Priority": new_priority
                        }
                        
                        if "Description" in tasks_df.columns:
                            new_task_data["Description"] = task_description
                        
                        tasks_df = pd.concat([tasks_df, pd.DataFrame([new_task_data])], ignore_index=True)
                        
                        if update_tasks_sheet(tasks_df):
                            st.success(f"✅ Task '{new_task_name}' assigned to {new_assignee}!")
                            st.rerun()
                    else:
                        st.warning("⚠️ Task name cannot be empty.")
        elif can_assign and not subordinates:
            st.info("ℹ️ You don't have any subordinates to assign tasks to.")
        else:
            st.info("ℹ️ You do not have permission to assign tasks.")
    
    with tab3:
        st.subheader("🔄 Update Task Status")
        if user_role == "Junior Head":
            user_tasks = view_df[view_df["AssignedTo"] == user_name]
        else:
            user_tasks = view_df  # Heads can update tasks they see

        if not user_tasks.empty:
            with st.form("update_status_form"):
                task_to_update = st.selectbox(
                    "Select Task", 
                    user_tasks["TaskID"].tolist(),
                    format_func=lambda x: f"ID {x}: {user_tasks[user_tasks['TaskID']==x]['TaskName'].iloc[0]}"
                )
                new_status = st.selectbox("New Status", ["Not Started", "In Progress", "Done"])
                
                # Show description input only if marking as Done
                completion_description = ""
                if new_status == "Done":
                    completion_description = st.text_area("Describe what you have completed (required)", max_chars=500)
                
                update_button = st.form_submit_button("🔄 Update Status")
                
                if update_button:
                    if new_status == "Done" and not completion_description.strip():
                        st.warning("Please provide a description of the completed work.")
                    else:
                        tasks_df.loc[tasks_df["TaskID"] == task_to_update, "Status"] = new_status
                        if new_status == "Done":
                            tasks_df.loc[tasks_df["TaskID"] == task_to_update, "Description"] = completion_description
                        if update_tasks_sheet(tasks_df):
                            st.success(f"✅ Task {task_to_update} updated to '{new_status}'!")
                            st.rerun()
        else:
            st.info("ℹ️ No tasks available for status update.")
    
    with tab4:
        st.subheader("❌ Delete Task")
        if user_role in ["Core Head", "Domain Head"]:
            if not view_df.empty:
                with st.form("delete_task_form"):
                    task_to_delete = st.selectbox(
                        "Select Task to Delete",
                        view_df["TaskID"].tolist(),
                        format_func=lambda x: f"ID {x}: {view_df[view_df['TaskID']==x]['TaskName'].iloc[0]}"
                    )
                    st.warning("⚠️ This action cannot be undone!")
                    confirm_delete = st.checkbox("I confirm I want to delete this task")
                    delete_button = st.form_submit_button("🗑️ Delete Task", type="secondary")
                    if delete_button and confirm_delete:
                        tasks_df = tasks_df[tasks_df["TaskID"] != task_to_delete]
                        if update_tasks_sheet(tasks_df):
                            st.success(f"✅ Task {task_to_delete} deleted successfully!")
                            st.rerun()
                    elif delete_button and not confirm_delete:
                        st.error("❌ Please confirm the deletion by checking the checkbox.")
            else:
                st.info("ℹ️ No tasks available to delete.")
        else:
            st.info("🔒 Only Core Heads and Domain Heads can delete tasks.")

# --- Main Application Logic ---
def main():
    # Custom CSS for better styling
    st.markdown("""
    <style>
        /* Fix metric card styling */
        div[data-testid="metric-container"] {
            background-color: rgba(40, 42, 54, 0.8) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            padding: 1rem !important;
            border-radius: 10px !important;
            border-left: 4px solid #4CAF50 !important;
        }
        
        div[data-testid="metric-container"] > div {
            color: white !important;
        }
        
        /* Metric value styling */
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: #4CAF50 !important;
            font-size: 2rem !important;
            font-weight: bold !important;
        }
        
        /* Metric label styling */
        div[data-testid="metric-container"] [data-testid="stMetricLabel"] {
            color: #ffffff !important;
            font-weight: 600 !important;
        }
        
        /* Tab styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            padding-left: 20px;
            padding-right: 20px;
            background-color: rgba(40, 42, 54, 0.5);
            border-radius: 5px;
            color: white;
            font-weight: bold;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #4CAF50 !important;
            color: white !important;
        }
        
        /* Info box styling */
        .stInfo {
            background-color: rgba(52, 144, 220, 0.1) !important;
            border: 1px solid rgba(52, 144, 220, 0.3) !important;
            color: white !important;
        }
        
        /* Success box styling */
        .stSuccess {
            background-color: rgba(76, 175, 80, 0.1) !important;
            border: 1px solid rgba(76, 175, 80, 0.3) !important;
            color: white !important;
        }
        
        /* Warning box styling */
        .stWarning {
            background-color: rgba(255, 193, 7, 0.1) !important;
            border: 1px solid rgba(255, 193, 7, 0.3) !important;
            color: white !important;
        }
        
        /* Error box styling */
        .stError {
            background-color: rgba(220, 53, 69, 0.1) !important;
            border: 1px solid rgba(220, 53, 69, 0.3) !important;
            color: white !important;
        }
        
        /* Dataframe styling */
        .stDataFrame {
            background-color: rgba(255, 255, 255, 0.05) !important;
            border-radius: 10px !important;
        }
        /* Remove white overlay from DataFrame cells */
        .stDataFrame [data-testid="stStyledTable"] td,
        .stDataFrame [data-testid="stStyledTable"] th,
        .stDataFrame tbody tr td,
        .stDataFrame td {
            background: inherit !important;
            background-color: inherit !important;
            opacity: 1 !important;
        }
        .stDataFrame [data-testid="stStyledTable"] td:before {
            background: none !important;
            content: none !important;
            opacity: 1 !important;
        }
        
        /* Form styling */
        .stForm {
            background-color: rgba(40, 42, 54, 0.3) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 10px !important;
            padding: 20px !important;
        }
        
        /* Button styling */
        .stButton > button {
            background-color: #4CAF50 !important;
            color: white !important;
            border: none !important;
            border-radius: 5px !important;
            font-weight: bold !important;
            transition: all 0.3s ease !important;
        }
        
        .stButton > button:hover {
            background-color: #45a049 !important;
            transform: translateY(-2px) !important;
        }
        
        /* Secondary button styling */
        .stButton > button[kind="secondary"] {
            background-color: #dc3545 !important;
            color: white !important;
        }
        
        .stButton > button[kind="secondary"]:hover {
            background-color: #c82333 !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Route to appropriate page
    if st.session_state.page == "register":
        show_register_page()
    elif st.session_state.authenticated:
        show_dashboard()
    else:
        show_login_page()

if __name__ == "__main__":
    main()