import streamlit as st
import httpx
import pandas as pd
import json

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="ProcureIQ: AI-Powered Vendor and Procurement Agent",
    page_icon="🔍",
    layout="wide",
)


def init_state():
    defaults = {
        "step": 1,
        "session_id": None,
        "extracted_items": [],
        "benchmarks": [],
        "reputations": [],
        "matrix": None,
        "email_text": None,
        "po_pdf_path": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def api_get(path: str, params: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        resp = httpx.get(f"{BACKEND_URL}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        st.error("Cannot connect to backend. Is FastAPI running on port 8000?")
        return {}
    except httpx.ReadTimeout:
        return {}
    except httpx.HTTPStatusError as e:
        st.error(f"API error: {e.response.status_code} — {e.response.text}")
        return {}


def api_post(path: str, data: dict | None = None, files: list | None = None) -> dict:
    try:
        if files:
            resp = httpx.post(f"{BACKEND_URL}{path}", files=files, timeout=300.0)
        else:
            resp = httpx.post(f"{BACKEND_URL}{path}", json=data, timeout=180.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ReadTimeout:
        st.error("Request timed out — the AI server took too long to respond. Try again or use smaller/different PDFs.")
        return {}
    except httpx.ConnectError:
        st.error("Cannot connect to backend. Is FastAPI running on port 8000?")
        return {}
    except httpx.HTTPStatusError as e:
        st.error(f"API error: {e.response.status_code} — {e.response.text}")
        return {}


def render_sidebar():
    with st.sidebar:
        st.title("🔍 ProcureIQ")
        st.caption("AI-Powered Vendor and Procurement Agent")

        step = st.session_state.step
        steps = ["Upload PDFs", "Review Data", "Research", "Analysis", "Close Deal"]
        for i, label in enumerate(steps, 1):
            if i < step:
                st.success(f"✓ {i}. {label}")
            elif i == step:
                st.info(f"▶ {i}. {label}")
            else:
                st.text(f"  {i}. {label}")

        st.divider()

        with st.expander("⚙️ Configuration"):
            config = api_get("/api/config/check", timeout=5.0)
            if config:
                if config.get("valid"):
                    st.success("All API keys configured")
                else:
                    missing = config.get("missing", [])
                    st.error(f"Missing: {', '.join(missing)}")
                    st.caption("Add keys to your .env file and restart")

        with st.expander("📊 Price History"):
            if st.button("Load History", key="load_history"):
                st.session_state.history_loaded = True
            if st.session_state.get("history_loaded"):
                history_data = api_get("/api/history", timeout=30.0)
                if history_data and isinstance(history_data, list):
                    df = pd.DataFrame(history_data)
                    if not df.empty and "item_price" in df.columns:
                        st.dataframe(
                            df[["vendor_name", "item_name", "item_price", "normalized_unit", "timestamp"]],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("No history yet")
                else:
                    st.info("No history yet or request timed out")
            else:
                st.caption("Click 'Load History' to fetch from database")


def render_step_1():
    st.header("Step 1: Upload Vendor Quotes")
    st.markdown("Upload one or more PDF quotes from vendors. The AI will extract and normalize all data.")

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files and st.button("Upload & Extract", type="primary"):
        with st.spinner("Parsing PDFs and extracting data with AI..."):
            files_list = [
                ("files", (f.name, f.getvalue(), "application/pdf"))
                for f in uploaded_files
            ]
            result = api_post("/api/upload", files=files_list)

        if result and "session_id" in result:
            # Clear any stale data from previous sessions
            st.session_state.benchmarks = []
            st.session_state.reputations = []
            st.session_state.matrix = None
            st.session_state.email_text = None
            st.session_state.po_pdf_path = None
            st.session_state.session_id = result["session_id"]
            st.session_state.extracted_items = result["extracted_items"]
            st.session_state.step = 2
            st.rerun()


def render_step_2():
    st.header("Step 2: Review Extracted Data")
    items = st.session_state.extracted_items

    if not items:
        st.warning("No items extracted. Go back and upload PDFs.")
        return

    st.success(f"Extracted {len(items)} item(s) from vendor quotes")

    for i, item in enumerate(items):
        with st.expander(f"📋 {item['vendor_name']} — {item['item_name']}", expanded=True):
            col1, col2, col3 = st.columns(3)
            qty = int(item['quantity']) if item['quantity'] == int(item['quantity']) else item['quantity']
            price_per_unit = item['item_price'] / max(item.get('normalized_quantity') or 1, 1)
            with col1:
                st.markdown(f"**Vendor:** {item['vendor_name']}")
                st.markdown(f"**Item:** {item['item_name']}")
                st.markdown(f"**Price:** RM {item['item_price']:,.2f}")
                st.markdown(f"**Quantity:** {qty} {item['unit']}")
            with col2:
                st.markdown(f"**Normalized Unit:** {item['normalized_unit']}")
                st.markdown(f"**Unit Price:** RM {price_per_unit:,.2f}/{item['normalized_unit']}")
                st.markdown(f"**Delivery:** {item.get('delivery_days', 'N/A')} days")
            with col3:
                st.markdown(f"**Payment:** {item.get('payment_terms', 'N/A')}")
                if item.get("hidden_fees"):
                    for fee in item["hidden_fees"]:
                        st.warning(f"⚠️ Hidden fee: {fee}")

            st.progress(item.get("confidence", 1.0), text=f"Extraction confidence: {item.get('confidence', 1.0):.0%}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("← Back to Upload"):
            st.session_state.step = 1
            st.rerun()
    with col_b:
        if st.button("Confirm & Continue →", type="primary"):
            st.session_state.step = 3
            st.rerun()


def render_step_3():
    st.header("Step 3: Adversarial Research")
    st.markdown("Scraping market prices and vendor reputations, then comparing against your quote history.")

    if st.button("🔍 Run Research", type="primary"):
        with st.spinner("Scraping market data and vendor reputations... This may take a minute."):
            result = api_post(
                "/api/research",
                data={"session_id": st.session_state.session_id},
            )

        if result and "market_benchmarks" in result:
            st.session_state.benchmarks = result["market_benchmarks"]
            st.session_state.reputations = result["reputation_results"]
            st.rerun()

    # Display results if available
    benchmarks = st.session_state.benchmarks
    reputations = st.session_state.reputations

    if benchmarks:
        st.subheader("Market Benchmarks")
        for bm in benchmarks:
            with st.expander(f"💲 {bm['item_name']}", expanded=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Low", f"RM {bm.get('market_price_low', 'N/A')}" if bm.get('market_price_low') else "N/A")
                with col2:
                    st.metric("Average", f"RM {bm.get('market_price_avg', 'N/A')}" if bm.get('market_price_avg') else "N/A")
                with col3:
                    st.metric("High", f"RM {bm.get('market_price_high', 'N/A')}" if bm.get('market_price_high') else "N/A")
                if bm.get("source_snippets"):
                    with st.expander("Sources"):
                        for s in bm["source_snippets"]:
                            st.caption(s)

    if reputations:
        st.subheader("Vendor Reputation")
        for rep in reputations:
            with st.expander(f"🏢 {rep['vendor_name']}", expanded=True):
                if rep.get("red_flags"):
                    st.error("Red Flags:")
                    for flag in rep["red_flags"]:
                        st.markdown(f"- 🚩 {flag}")
                if rep.get("positive_notes"):
                    st.success("Positive Notes:")
                    for note in rep["positive_notes"]:
                        st.markdown(f"- ✅ {note}")
                if not rep.get("red_flags") and not rep.get("positive_notes"):
                    st.info("No reputation data found")

    if benchmarks or reputations:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("← Back to Review"):
                st.session_state.step = 2
                st.rerun()
        with col_b:
            if st.button("Continue to Analysis →", type="primary"):
                st.session_state.step = 4
                st.rerun()


def render_step_4():
    st.header("Step 4: Competitive Matrix")
    st.markdown("AI-powered adversarial analysis across all vendors.")

    if not st.session_state.matrix:
        if st.button("🧠 Run Adversarial Analysis", type="primary"):
            with st.spinner("AI is analyzing all data — finding every reason NOT to choose each vendor..."):
                result = api_post(
                    "/api/analyze",
                    data={"session_id": st.session_state.session_id},
                )
            if result and "competitive_matrix" in result:
                st.session_state.matrix = result["competitive_matrix"]
                st.rerun()
        return

    matrix = st.session_state.matrix

    # Winner banner
    st.success(f"🏆 Recommended Winner: **{matrix['winner']}**")
    with st.expander("Winner Justification"):
        st.write(matrix["winner_justification"])

    # Vendor comparison columns
    st.subheader("Vendor Comparison")
    analyses = matrix.get("analyses", [])

    if analyses:
        cols = st.columns(len(analyses))
        for col, analysis in zip(cols, analyses):
            with col:
                score = analysis["overall_score"]
                score_color = "green" if score >= 7 else "orange" if score >= 4 else "red"

                st.markdown(f"### {analysis['vendor_name']}")
                st.markdown(
                    f"<h2 style='color:{score_color};'>Score: {score}/10</h2>",
                    unsafe_allow_html=True,
                )
                st.progress(score / 10)

                st.markdown("---")

                def risk_label(val, field=""):
                    if val in ("high", "above", "higher"):
                        return f"🔴 **{field}:** {val}"
                    elif val in ("medium", "at", "same"):
                        return f"🟡 **{field}:** {val}"
                    else:
                        return f"🟢 **{field}:** {val}"

                st.markdown(risk_label(analysis["price_vs_market"], "Price vs Market"))
                st.markdown(risk_label(analysis["price_vs_history"], "Price vs History"))

                if analysis["hidden_fee_alert"]:
                    st.error("⚠️ Hidden fees detected!")
                else:
                    st.success("No hidden fees")

                st.markdown(risk_label(analysis["reputation_risk"], "Reputation Risk"))
                st.markdown(risk_label(analysis["delivery_risk"], "Delivery Risk"))

                with st.expander("Summary"):
                    st.write(analysis["summary"])

    # Comparison table
    st.subheader("Side-by-Side Comparison")
    table_data = []
    for a in analyses:
        table_data.append({
            "Vendor": a["vendor_name"],
            "Score": f"{a['overall_score']}/10",
            "Price vs Market": a["price_vs_market"],
            "Price vs History": a["price_vs_history"],
            "Hidden Fees": "Yes" if a["hidden_fee_alert"] else "No",
            "Reputation": a["reputation_risk"],
            "Delivery": a["delivery_risk"],
        })
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

    # Vendor selection
    st.subheader("Select Vendor")
    vendor_names = [a["vendor_name"] for a in analyses]
    selected = st.selectbox("Choose a vendor to close the deal:", vendor_names)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("← Back to Research"):
            st.session_state.step = 3
            st.rerun()
    with col_b:
        if st.button(f"Accept {selected} & Generate PO →", type="primary"):
            with st.spinner("Drafting acceptance email and generating Purchase Order PDF..."):
                result = api_post(
                    "/api/accept",
                    data={
                        "session_id": st.session_state.session_id,
                        "vendor_name": selected,
                    },
                )
            if result and "email_text" in result:
                st.session_state.email_text = result["email_text"]
                st.session_state.po_pdf_path = result["po_pdf_path"]
                st.session_state.selected_vendor = selected
                st.session_state.step = 5
                st.rerun()


def render_step_5():
    st.header("Step 5: Close the Deal")
    vendor = st.session_state.get("selected_vendor", "Vendor")
    st.success(f"Deal closed with **{vendor}**!")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Acceptance Email")
        email = st.session_state.email_text or ""
        edited_email = st.text_area(
            "Review and edit the email before sending:",
            value=email,
            height=400,
            key="email_editor",
        )
        if edited_email:
            st.download_button(
                "📥 Download Email as Text",
                data=edited_email,
                file_name=f"acceptance_{vendor}.txt",
                mime="text/plain",
            )

    with col2:
        st.subheader("Purchase Order PDF")
        po_path = st.session_state.po_pdf_path
        if po_path:
            filename = po_path.split("/")[-1].split("\\")[-1]
            session_id = st.session_state.session_id

            download_url = f"{BACKEND_URL}/api/download/{session_id}/{filename}"

            st.markdown(f"📄 **{filename}**")
            try:
                with open(po_path, "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    "📥 Download PO PDF",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                )
            except FileNotFoundError:
                st.warning("PDF file not found on disk. Try regenerating.")

    st.divider()

    if st.button("🔄 Start New Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def main():
    init_state()
    render_sidebar()

    step = st.session_state.step

    if step == 1:
        render_step_1()
    elif step == 2:
        render_step_2()
    elif step == 3:
        render_step_3()
    elif step == 4:
        render_step_4()
    elif step == 5:
        render_step_5()


if __name__ == "__main__":
    main()
