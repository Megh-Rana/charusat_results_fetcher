import requests
from bs4 import BeautifulSoup
import os
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import curses

BASE_URL = "https://support.charusat.edu.in/Uniexamresult/"

# ---------------- CONFIG ----------------
MAX_WORKERS = 5        # each worker walks dropdowns once, then chains searches
ROLL_LIMIT = 120       # safe upper bound for bulk
REQUEST_TIMEOUT = 20
# ---------------------------------------


# ========== HTTP HELPERS ==========

def new_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded"
    })
    return s


def get_page(session):
    r = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def post(session, data):
    r = session.post(BASE_URL, data=data, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def get_hidden(html):
    soup = BeautifulSoup(html, "html.parser")
    return {
        i["name"]: i.get("value", "")
        for i in soup.select("input[type=hidden]")
        if i.get("name")
    }


def extract_select_options(html, name):
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", {"name": name})
    out = []
    if not sel:
        return out
    for o in sel.find_all("option"):
        if o.get("value") and o["value"] != "0":
            out.append((o["value"], o.text.strip()))
    return out


# ========== WEBFORMS WALK ==========

def select_value(session, html, target, values):
    h = get_hidden(html)
    h["__EVENTTARGET"] = target
    h.update(values)
    return post(session, h)


def fetch_one(inst, degree, sem, exam, enr):
    """
    One complete, isolated fetch.
    """
    session = new_session()
    start = time.time()

    try:
        html = get_page(session)

        html = select_value(session, html, "ddlInst", {
            "ddlInst": inst
        })

        html = select_value(session, html, "ddlDegree", {
            "ddlInst": inst,
            "ddlDegree": degree
        })

        html = select_value(session, html, "ddlSem", {
            "ddlInst": inst,
            "ddlDegree": degree,
            "ddlSem": sem
        })

        html = select_value(session, html, "ddlScheduleExam", {
            "ddlInst": inst,
            "ddlDegree": degree,
            "ddlSem": sem,
            "ddlScheduleExam": exam
        })

        h = get_hidden(html)
        h.update({
            "ddlInst": inst,
            "ddlDegree": degree,
            "ddlSem": sem,
            "ddlScheduleExam": exam,
            "txtEnrNo": enr,
            "btnSearch": "Search"
        })

        html = post(session, h)

        if "uclGrdNEP_lblSGPA" not in html:
            return None, time.time() - start

        soup = BeautifulSoup(html, "html.parser")
        sgpa = soup.find(id="uclGrdNEP_lblSGPA")
        credits = soup.find(id="uclGrdNEP_lblTotCredit")

        return {
            "roll": enr,
            "sgpa": sgpa.text.strip() if sgpa else None,
            "credits": credits.text.strip() if credits else None,
            "html": html
        }, time.time() - start

    except Exception:
        return None, time.time() - start


def prepare_session(inst, degree, sem, exam):
    """
    Walk through all dropdowns once and return (session, ready_html).
    The returned html contains the ViewState needed to submit searches.
    """
    session = new_session()
    html = get_page(session)

    html = select_value(session, html, "ddlInst", {
        "ddlInst": inst
    })
    html = select_value(session, html, "ddlDegree", {
        "ddlInst": inst,
        "ddlDegree": degree
    })
    html = select_value(session, html, "ddlSem", {
        "ddlInst": inst,
        "ddlDegree": degree,
        "ddlSem": sem
    })
    html = select_value(session, html, "ddlScheduleExam", {
        "ddlInst": inst,
        "ddlDegree": degree,
        "ddlSem": sem,
        "ddlScheduleExam": exam
    })
    return session, html


def search_with_session(session, html, inst, degree, sem, exam, enr):
    """
    Submit a single search using an already-prepared session.
    Returns (result_dict | None, elapsed, new_html).
    The new_html should be passed to the next call to keep ViewState fresh.
    """
    start = time.time()
    try:
        h = get_hidden(html)
        h.update({
            "ddlInst": inst,
            "ddlDegree": degree,
            "ddlSem": sem,
            "ddlScheduleExam": exam,
            "txtEnrNo": enr,
            "btnSearch": "Search"
        })
        result_html = post(session, h)

        if "uclGrdNEP_lblSGPA" not in result_html:
            return None, time.time() - start, result_html

        soup = BeautifulSoup(result_html, "html.parser")
        sgpa = soup.find(id="uclGrdNEP_lblSGPA")
        credits = soup.find(id="uclGrdNEP_lblTotCredit")

        return {
            "roll": enr,
            "sgpa": sgpa.text.strip() if sgpa else None,
            "credits": credits.text.strip() if credits else None,
            "html": result_html
        }, time.time() - start, result_html

    except Exception:
        return None, time.time() - start, html


def worker_batch(inst, degree, sem, exam, enrollments):
    """
    Process a batch of enrollment numbers using a single prepared session.
    Walks dropdowns once, then chains searches (~1s each instead of ~21s).
    """
    session, html = prepare_session(inst, degree, sem, exam)
    results = []
    for enr in enrollments:
        result, elapsed, html = search_with_session(
            session, html, inst, degree, sem, exam, enr
        )
        results.append((result, elapsed))
    return results


# ========== CURSES MENU (ARROW KEYS) ==========

def menu(stdscr, title, options):
    curses.curs_set(0)
    idx = 0

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, title, curses.A_BOLD)

        for i, (_, label) in enumerate(options):
            if i == idx:
                stdscr.addstr(i + 2, 2, f"> {label}", curses.A_REVERSE)
            else:
                stdscr.addstr(i + 2, 2, f"  {label}")

        key = stdscr.getch()

        if key == curses.KEY_UP and idx > 0:
            idx -= 1
        elif key == curses.KEY_DOWN and idx < len(options) - 1:
            idx += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return options[idx][0]


def curses_select(title, options):
    return curses.wrapper(lambda stdscr: menu(stdscr, title, options))


# ========== SINGLE MODE ==========

def single_run(inst, degree, sem, exam):
    enr = input("\nEnter full enrollment number (e.g. 25CE099): ").strip()

    print("\nFetching result...")
    result, elapsed = fetch_one(inst, degree, sem, exam, enr)

    if not result:
        print("No result found.")
        return

    print(f"\n[{elapsed:.2f}s] {enr}")
    print("SGPA:", result["sgpa"])
    print("Credits:", result["credits"])

    os.makedirs("results/html", exist_ok=True)
    with open(f"results/html/{enr}.html", "w", encoding="utf-8") as f:
        f.write(result["html"])

    print(f"Saved HTML → results/html/{enr}.html")


# ========== BULK MODE ==========

def bulk_run(inst, degree, sem, exam, prefix):
    os.makedirs("results/html", exist_ok=True)

    rows = []
    highest = 0.0
    topper = None

    # Split enrollment numbers into chunks, one per worker
    all_enr = [f"{prefix}{i:03d}" for i in range(1, ROLL_LIMIT + 1)]
    chunk_size = (len(all_enr) + MAX_WORKERS - 1) // MAX_WORKERS
    chunks = [all_enr[i:i + chunk_size] for i in range(0, len(all_enr), chunk_size)]

    print(f"\nRunning bulk with {MAX_WORKERS} workers "
          f"({chunk_size} rolls each, session reuse)...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(worker_batch, inst, degree, sem, exam, chunk)
            for chunk in chunks
        ]

        for fut in as_completed(futures):
            for result, elapsed in fut.result():
                if not result:
                    continue

                enr = result["roll"]
                sgpa = result["sgpa"]

                print(f"[{elapsed:5.2f}s] {enr}  SGPA={sgpa}")

                rows.append([enr, sgpa, result["credits"]])

                try:
                    s = float(sgpa)
                    if s > highest:
                        highest = s
                        topper = enr
                except:
                    pass

                with open(f"results/html/{enr}.html", "w", encoding="utf-8") as f:
                    f.write(result["html"])

    with open("results/sgpa_summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Roll No", "SGPA", "Credits"])
        writer.writerows(rows)

    print("\nDone.")
    print("Total results:", len(rows))
    if topper:
        print(f"Highest SGPA: {highest} ({topper})")


# ========== MAIN ==========

def main():
    base_session = new_session()
    html = get_page(base_session)

    inst_opts = extract_select_options(html, "ddlInst")
    inst = curses_select("Select Institute (↑ ↓ Enter)", inst_opts)

    html = select_value(base_session, html, "ddlInst", {"ddlInst": inst})
    deg_opts = extract_select_options(html, "ddlDegree")
    degree = curses_select("Select Degree", deg_opts)

    html = select_value(base_session, html, "ddlDegree", {
        "ddlInst": inst,
        "ddlDegree": degree
    })

    sem_opts = extract_select_options(html, "ddlSem")
    sem = curses_select("Select Semester", sem_opts)

    html = select_value(base_session, html, "ddlSem", {
        "ddlInst": inst,
        "ddlDegree": degree,
        "ddlSem": sem
    })

    exam_opts = extract_select_options(html, "ddlScheduleExam")
    exam = curses_select("Select Exam", exam_opts)

    mode = curses_select(
        "Select Mode",
        [
            ("single", "Single result"),
            ("bulk", "Bulk download"),
        ]
    )

    if mode == "single":
        single_run(inst, degree, sem, exam)
    else:
        prefix = input("\nEnter roll prefix (e.g. 25CE): ").strip()
        bulk_run(inst, degree, sem, exam, prefix)


if __name__ == "__main__":
    main()
