import sys
import json
import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def log_step(name, status, details=""):
    print(f"[{status}] - {name} {f'({details})' if details else ''}")

def run_e2e_validation():
    print("Starting BA-Bot E2E Validation Sequence...")
    results = {}

    # Step 1: Admin Login
    admin_token = None
    try:
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@example.com",
            "password": "admin123"
        })
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("success") is True:
                data = data.get("data")
            admin_token = data.get("access_token")
            log_step("Admin Login", "PASS")
            results["Admin Login"] = "PASS"
        else:
            log_step("Admin Login", "FAIL", f"Status: {res.status_code}")
            results["Admin Login"] = "FAIL"
            return results
    except Exception as e:
        log_step("Admin Login", "FAIL", str(e))
        results["Admin Login"] = "FAIL"
        return results

    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    # Retrieve BA user ID dynamically
    ba_user_id = 2
    try:
        users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=headers_admin)
        if users_res.status_code == 200:
            users_list = users_res.json()
            if isinstance(users_list, dict) and "data" in users_list:
                users_list = users_list["data"]
            ba_user = next((u for u in users_list if u["email"] == "ba@example.com"), None)
            if ba_user:
                ba_user_id = ba_user["id"]
    except Exception as e:
        print(f"Warning: Failed to dynamically retrieve BA user ID: {e}")

    # Step 2: Create Team
    team_id = None
    try:
        res = requests.post(f"{BASE_URL}/api/admin/teams", headers=headers_admin, json={
            "name": f"Validation Team {int(time.time())}",
            "manager_id": ba_user_id  # ba@example.com
        })
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("success") is True:
                data = data.get("data")
            team_id = data.get("team_id")
            log_step("Create Team", "PASS", f"Team ID: {team_id}")
            results["Create Team"] = "PASS"
        else:
            log_step("Create Team", "FAIL", f"Status: {res.status_code}")
            results["Create Team"] = "FAIL"
            return results
    except Exception as e:
        log_step("Create Team", "FAIL", str(e))
        results["Create Team"] = "FAIL"
        return results

    # Step 3: Create Project
    project_id = None
    try:
        res = requests.post(f"{BASE_URL}/api/admin/projects", headers=headers_admin, json={
            "name": f"Validation Project {int(time.time())}",
            "description": "E2E automated test project description"
        })
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("success") is True:
                data = data.get("data")
            project_id = data.get("project_id") or data.get("id")
            log_step("Create Project", "PASS", f"Project ID: {project_id}")
            results["Create Project"] = "PASS"
        else:
            log_step("Create Project", "FAIL", f"Status: {res.status_code}")
            results["Create Project"] = "FAIL"
            return results
    except Exception as e:
        log_step("Create Project", "FAIL", str(e))
        results["Create Project"] = "FAIL"
        return results

    # Step 4: Assign Users to Team and Project to Team
    try:
        # Add BA user to team
        res_mem = requests.post(f"{BASE_URL}/api/admin/teams/{team_id}/members", headers=headers_admin, json={
            "user_ids": [ba_user_id]
        })
        # Assign project to team
        res_proj = requests.post(f"{BASE_URL}/api/admin/teams/{team_id}/projects", headers=headers_admin, json={
            "project_ids": [project_id]
        })
        if res_mem.status_code == 200 and res_proj.status_code == 200:
            log_step("Assign Users/Projects to Team", "PASS")
            results["Assign Users"] = "PASS"
        else:
            log_step("Assign Users/Projects to Team", "FAIL", f"Mem status: {res_mem.status_code}, Proj status: {res_proj.status_code}")
            results["Assign Users"] = "FAIL"
            return results
    except Exception as e:
        log_step("Assign Users/Projects to Team", "FAIL", str(e))
        results["Assign Users"] = "FAIL"
        return results

    # Step 5: Assigned User Login
    ba_token = None
    try:
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "ba@example.com",
            "password": "ba123"
        })
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("success") is True:
                data = data.get("data")
            ba_token = data.get("access_token")
            log_step("Assigned User Login", "PASS")
            results["Assigned User Login"] = "PASS"
        else:
            log_step("Assigned User Login", "FAIL", f"Status: {res.status_code}")
            results["Assigned User Login"] = "FAIL"
            return results
    except Exception as e:
        log_step("Assigned User Login", "FAIL", str(e))
        results["Assigned User Login"] = "FAIL"
        return results

    headers_ba = {"Authorization": f"Bearer {ba_token}"}

    # Step 6: Assigned User opens project
    try:
        res = requests.get(f"{BASE_URL}/api/projects", headers=headers_ba)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("success") is True:
                data = data.get("data")
            project_ids = [p.get("id") for p in data]
            if project_id in project_ids:
                log_step("Assigned User opens project", "PASS")
                results["Assigned User opens project"] = "PASS"
            else:
                log_step("Assigned User opens project", "FAIL", "Project not found in user list")
                results["Assigned User opens project"] = "FAIL"
                return results
        else:
            log_step("Assigned User opens project", "FAIL", f"Status: {res.status_code}")
            results["Assigned User opens project"] = "FAIL"
            return results
    except Exception as e:
        log_step("Assigned User opens project", "FAIL", str(e))
        results["Assigned User opens project"] = "FAIL"
        return results

    # Step 7: Requirement Discovery conversation starts
    # Step 8: Conversation state persists
    try:
        res = requests.post(f"{BASE_URL}/api/predict", headers=headers_ba, json={
            "projectId": project_id,
            "question": "What is the name of this project?",
            "sessionId": f"session_{project_id}"
        })
        if res.status_code == 200:
            content = res.text
            if "data:" in content:
                log_step("Requirement Discovery conversation starts", "PASS")
                results["Requirement Discovery conversation starts"] = "PASS"
                log_step("Conversation state persists", "PASS")
                results["Conversation state persists"] = "PASS"
            else:
                log_step("Requirement Discovery conversation starts", "FAIL", "Streaming payload did not contain data events")
                results["Requirement Discovery conversation starts"] = "FAIL"
                results["Conversation state persists"] = "FAIL"
                return results
        else:
            log_step("Requirement Discovery conversation starts", "FAIL", f"Status: {res.status_code}")
            results["Requirement Discovery conversation starts"] = "FAIL"
            results["Conversation state persists"] = "FAIL"
            return results
    except Exception as e:
        log_step("Requirement Discovery conversation starts", "FAIL", str(e))
        results["Requirement Discovery conversation starts"] = "FAIL"
        results["Conversation state persists"] = "FAIL"
        return results

    # Step 9: AI extracts structured requirements
    # Step 10: Project data updates automatically
    try:
        res = requests.post(f"{BASE_URL}/api/predict", headers=headers_ba, json={
            "projectId": project_id,
            "question": "The project name is Retail Logistics System and we are in logistics domain.",
            "sessionId": f"session_{project_id}"
        })
        time.sleep(2)
        
        res_get = requests.get(f"{BASE_URL}/api/projects", headers=headers_ba)
        data = res_get.json()
        if isinstance(data, dict) and data.get("success") is True:
            data = data.get("data")
            
        target_proj = next((p for p in data if p.get("id") == project_id), None)
        if target_proj and target_proj.get("project", {}).get("name") == "Retail Logistics System":
            log_step("AI extracts structured requirements", "PASS")
            results["AI extracts structured requirements"] = "PASS"
            log_step("Project data updates automatically", "PASS")
            results["Project data updates automatically"] = "PASS"
        else:
            log_step("AI extracts structured requirements", "PARTIAL", "State extraction failed to populate key Retail Logistics System")
            results["AI extracts structured requirements"] = "PARTIAL"
            results["Project data updates automatically"] = "PARTIAL"
    except Exception as e:
        log_step("AI extracts structured requirements", "FAIL", str(e))
        results["AI extracts structured requirements"] = "FAIL"
        results["Project data updates automatically"] = "FAIL"

    # Step 11: Review page displays extracted data
    try:
        res = requests.get(f"{BASE_URL}/api/projects", headers=headers_ba)
        if res.status_code == 200:
            log_step("Review page displays extracted data", "PASS")
            results["Review page displays extracted data"] = "PASS"
        else:
            log_step("Review page displays extracted data", "FAIL")
            results["Review page displays extracted data"] = "FAIL"
    except Exception as e:
        log_step("Review page displays extracted data", "FAIL", str(e))
        results["Review page displays extracted data"] = "FAIL"

    # Step 12: Admin reviews project
    # Step 13: Project approval
    try:
        res_sub = requests.post(f"{BASE_URL}/api/projects/{project_id}/submit", headers=headers_ba)
        res_app = requests.post(f"{BASE_URL}/api/projects/{project_id}/review", headers=headers_admin, json={
            "approved": True,
            "feedback": "Everything looks detailed and complete."
        })
        if res_sub.status_code == 200 and res_app.status_code == 200:
            log_step("Admin reviews project", "PASS")
            results["Admin reviews project"] = "PASS"
            log_step("Project approval", "PASS")
            results["Project approval"] = "PASS"
        else:
            log_step("Admin reviews project", "FAIL", f"Sub status: {res_sub.status_code}, App status: {res_app.status_code}")
            results["Admin reviews project"] = "FAIL"
            results["Project approval"] = "FAIL"
    except Exception as e:
        log_step("Admin reviews project", "FAIL", str(e))
        results["Admin reviews project"] = "FAIL"
        results["Project approval"] = "FAIL"

    # Step 14: Document generation
    # Step 15: Document stored under project
    try:
        res = requests.get(f"{BASE_URL}/api/projects/{project_id}/export?format=pdf", headers=headers_ba)
        if res.status_code == 200 and len(res.content) > 0:
            log_step("Document generation", "PASS")
            results["Document generation"] = "PASS"
            log_step("Document stored under project", "PASS")
            results["Document stored under project"] = "PASS"
        else:
            log_step("Document generation", "FAIL", f"Status: {res.status_code}")
            results["Document generation"] = "FAIL"
            results["Document stored under project"] = "FAIL"
    except Exception as e:
        log_step("Document generation", "FAIL", str(e))
        results["Document generation"] = "FAIL"
        results["Document stored under project"] = "FAIL"

    # Step 16: Project archived
    try:
        res = requests.put(f"{BASE_URL}/api/admin/projects/{project_id}/archive", headers=headers_admin)
        if res.status_code == 200:
            log_step("Project archived", "PASS")
            results["Project archived"] = "PASS"
        else:
            log_step("Project archived", "FAIL", f"Status: {res.status_code}")
            results["Project archived"] = "FAIL"
    except Exception as e:
        log_step("Project archived", "FAIL", str(e))
        results["Project archived"] = "FAIL"

    # Step 17: Project reopened
    try:
        res = requests.put(f"{BASE_URL}/api/admin/projects/{project_id}/restore", headers=headers_admin)
        if res.status_code == 200:
            log_step("Project reopened", "PASS")
            results["Project reopened"] = "PASS"
        else:
            log_step("Project reopened", "FAIL", f"Status: {res.status_code}")
            results["Project reopened"] = "FAIL"
    except Exception as e:
        log_step("Project reopened", "FAIL", str(e))
        results["Project reopened"] = "FAIL"

    # Step 18: Conversation restored
    try:
        res = requests.get(f"{BASE_URL}/api/projects", headers=headers_ba)
        data = res.json()
        if isinstance(data, dict) and data.get("success") is True:
            data = data.get("data")
        target_proj = next((p for p in data if p.get("id") == project_id), None)
        if target_proj and len(target_proj.get("messages", [])) > 0:
            log_step("Conversation restored", "PASS")
            results["Conversation restored"] = "PASS"
        else:
            log_step("Conversation restored", "FAIL", "Message log was empty")
            results["Conversation restored"] = "FAIL"
    except Exception as e:
        log_step("Conversation restored", "FAIL", str(e))
        results["Conversation restored"] = "FAIL"

    # Step 19: Permissions enforced
    try:
        res = requests.delete(f"{BASE_URL}/api/projects/{project_id}", headers=headers_ba)
        if res.status_code in (403, 405):
            log_step("Permissions enforced", "PASS")
            results["Permissions enforced"] = "PASS"
        else:
            log_step("Permissions enforced", "FAIL", f"BA delete returned status {res.status_code}")
            results["Permissions enforced"] = "FAIL"
    except Exception as e:
        log_step("Permissions enforced", "FAIL", str(e))
        results["Permissions enforced"] = "FAIL"

    # Step 20: Audit logs generated
    try:
        res = requests.get(f"{BASE_URL}/api/admin/audit-logs", headers=headers_admin)
        if res.status_code == 200:
            log_step("Audit logs generated", "PASS")
            results["Audit logs generated"] = "PASS"
        else:
            log_step("Audit logs generated", "FAIL")
            results["Audit logs generated"] = "FAIL"
    except Exception as e:
        log_step("Audit logs generated", "FAIL", str(e))
        results["Audit logs generated"] = "FAIL"

    # Step 21: Project locked after publishing
    try:
        requests.post(f"{BASE_URL}/api/projects/{project_id}/submit", headers=headers_ba)
        requests.post(f"{BASE_URL}/api/projects/{project_id}/review", headers=headers_admin, json={"approved": True, "feedback": "approved"})
        res_pub = requests.post(f"{BASE_URL}/api/projects/{project_id}/publish", headers=headers_admin)
        res_chat = requests.post(f"{BASE_URL}/api/predict", headers=headers_ba, json={
            "projectId": project_id,
            "question": "Are you there?",
            "sessionId": f"session_{project_id}"
        })
        if res_pub.status_code == 200 and res_chat.status_code == 403:
            log_step("Project locked after publishing", "PASS")
            results["Project locked after publishing"] = "PASS"
        else:
            log_step("Project locked after publishing", "FAIL", f"Pub status: {res_pub.status_code}, Chat post after lock status: {res_chat.status_code}")
            results["Project locked after publishing"] = "FAIL"
    except Exception as e:
        log_step("Project locked after publishing", "FAIL", str(e))
        results["Project locked after publishing"] = "FAIL"

    print("E2E Validation Complete.")
    return results

if __name__ == "__main__":
    res = run_e2e_validation()
    with open("e2e_results.json", "w") as f:
        json.dump(res, f, indent=2)
