const ROLE_KEY = "hr_chat_role";

export function getStoredRole() {
  return localStorage.getItem(ROLE_KEY) || "employee";
}

export function RoleToggle({ role, onChange }) {
  function setRole(value) {
    localStorage.setItem(ROLE_KEY, value);
    onChange(value);
  }

  return (
    <div className="role-toggle">
      <span className="role-label">I am:</span>
      <button
        className={`role-btn ${role === "employee" ? "active" : ""}`}
        onClick={() => setRole("employee")}
      >
        Employee
      </button>
      <button
        className={`role-btn ${role === "hr" ? "active" : ""}`}
        onClick={() => setRole("hr")}
      >
        HR Professional
      </button>
    </div>
  );
}
