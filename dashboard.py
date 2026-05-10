import streamlit as st
import pandas as pd
from datetime import datetime

from storage import get_session_summaries, get_trades_for_session


def format_duration(total_seconds):
    total_seconds = max(int(total_seconds), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

st.set_page_config(page_title="OBI Trading Bot Dashboard", layout="wide")

st.title("📊 OBI Bot: Trade Analysis Dashboard")

# 1. Sidebar for Session Selection
st.sidebar.header("Data Sources")
all_sessions = get_session_summaries()
all_options = []
for session in all_sessions:
    started_at = session.get("started_at")
    if isinstance(started_at, datetime):
        label_time = started_at.strftime("%Y-%m-%d %H:%M:%S")
    else:
        label_time = str(started_at or session["session_id"])

    prefix = "🔴 ACTIVE SESSION" if session.get("status") == "ACTIVE" else "📦 ARCHIVED SESSION"
    start_capital = float(session.get("starting_capital", 0.0) or 0.0)
    end_capital = session.get("ending_capital")
    capital_label = (
        f"Capital {start_capital:.2f} -> {float(end_capital):.2f}"
        if end_capital is not None
        else f"Capital {start_capital:.2f}"
    )
    label = f"{prefix} | {label_time} | {capital_label} | {session['trade_count']} events"
    all_options.append((label, session["session_id"]))

if not all_options:
    st.info("No MongoDB trade sessions found. Make sure bot is running and MongoDB Atlas is configured.")
    st.stop()

selected_option = st.sidebar.selectbox("Select session to analyze", all_options, format_func=lambda x: x[0])
selected_session_id = selected_option[1]
view_mode = st.sidebar.radio("View", ["Trade Analysis", "Overview"])

if selected_session_id:
    df = pd.DataFrame(get_trades_for_session(selected_session_id))
    if df.empty:
        st.info("No trades stored for selected session yet.")
        st.stop()
    
    # Parse timestamps for reliable ordering when deriving open trades.
    if 'Time' in df.columns:
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
        df = df.sort_values(by='Time', ascending=True)
    
    # Data Cleaning: Ensure PNL columns are numeric
    df['PNL%'] = pd.to_numeric(df['PNL%'], errors='coerce')
    if 'PNL_USDT' in df.columns:
        df['PNL_USDT'] = pd.to_numeric(df['PNL_USDT'], errors='coerce')
    else:
        df['PNL_USDT'] = pd.NA

    if 'NotionalUSDT' in df.columns:
        df['NotionalUSDT'] = pd.to_numeric(df['NotionalUSDT'], errors='coerce')

    if 'Leverage' in df.columns:
        df['Leverage'] = pd.to_numeric(df['Leverage'], errors='coerce')

    df_closed = df[df['Status'].isin(['TP_HIT', 'SL_HIT'])].copy()

    if df_closed['PNL_USDT'].isna().all() and 'NotionalUSDT' in df_closed.columns:
        side_sign = df_closed['Side'].map({'LONG': 1, 'SHORT': -1}).fillna(0)
        move = ((df_closed['Exit'] - df_closed['Entry']) / df_closed['Entry']) * side_sign
        df_closed['PNL_USDT'] = df_closed['NotionalUSDT'] * move

    if view_mode == "Overview":
        st.subheader("📅 Monthly Overview (Daily USDT Profit)")

        if 'Time' not in df.columns or df['Time'].dropna().empty:
            st.info("No valid timestamps in selected session.")
            st.stop()

        available_months = sorted(df['Time'].dropna().dt.to_period('M').astype(str).unique())
        if not available_months:
            st.info("No month data found.")
            st.stop()

        selected_month = st.sidebar.selectbox("Month", available_months, index=len(available_months) - 1)
        month_period = pd.Period(selected_month)

        monthly_closed = df_closed[df_closed['Time'].dt.to_period('M') == month_period].copy()
        monthly_closed['Day'] = monthly_closed['Time'].dt.day

        days = pd.date_range(month_period.start_time, month_period.end_time, freq='D')
        full_days = pd.DataFrame({'Date': days})
        full_days['Day'] = full_days['Date'].dt.day

        daily = monthly_closed.groupby('Day', as_index=False)['PNL_USDT'].sum()
        overview = full_days[['Day']].merge(daily, on='Day', how='left').fillna({'PNL_USDT': 0.0})
        overview['PNL_USDT'] = overview['PNL_USDT'].round(2)

        total_month_usdt = overview['PNL_USDT'].sum()
        positive_days = int((overview['PNL_USDT'] > 0).sum())
        negative_days = int((overview['PNL_USDT'] < 0).sum())

        m1, m2, m3 = st.columns(3)
        m1.metric("Month Profit (USDT)", f"{total_month_usdt:.2f}")
        m2.metric("Profitable Days", positive_days)
        m3.metric("Losing Days", negative_days)

        st.bar_chart(overview.set_index('Day')['PNL_USDT'])
        st.dataframe(overview, use_container_width=True)
        st.stop()

    # Infer currently open trades from event stream.
    active_by_symbol = {}
    for _, row in df.iterrows():
        symbol = row.get('Symbol')
        status = row.get('Status')
        if pd.isna(symbol) or pd.isna(status):
            continue

        if status == 'OPEN':
            active_by_symbol[symbol] = row
        elif status in ['TP_HIT', 'SL_HIT']:
            active_by_symbol.pop(symbol, None)

    if active_by_symbol:
        df_open = pd.DataFrame(list(active_by_symbol.values())).copy()
    else:
        df_open = pd.DataFrame(columns=df.columns)

    # 2. Top Level Metrics
    total_trades = len(df_closed)
    wins = len(df_closed[df_closed['Status'] == 'TP_HIT'])
    losses = len(df_closed[df_closed['Status'] == 'SL_HIT'])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = df_closed['PNL%'].sum()
    total_pnl_usdt = df_closed['PNL_USDT'].sum(skipna=True)
    open_trades = len(df_open)
    current_session = next((session for session in all_sessions if session['session_id'] == selected_session_id), None)
    starting_capital = float(current_session.get('starting_capital', 0.0)) if current_session else 0.0
    ending_capital = current_session.get('ending_capital') if current_session else None

    session_runtime = "00:00:00"
    if 'Time' in df.columns and not df['Time'].dropna().empty:
        start_time = df['Time'].dropna().min()
        end_time = df['Time'].dropna().max()
        session_runtime = format_duration((end_time - start_time).total_seconds())

    worst_symbol = "N/A"
    worst_symbol_pnl = 0.0
    if not df_closed.empty:
        symbol_stats = df_closed.groupby('Symbol')['PNL%'].sum().sort_values()
        if not symbol_stats.empty:
            worst_symbol = symbol_stats.index[0]
            worst_symbol_pnl = float(symbol_stats.iloc[0])

    avg_leverage = 0.0
    if 'Leverage' in df_open.columns and not df_open.empty:
        avg_leverage = float(df_open['Leverage'].dropna().mean()) if not df_open['Leverage'].dropna().empty else 0.0

    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
    col1.metric("Total Closed Trades", total_trades)
    col2.metric("Win Rate", f"{win_rate:.2f}%")
    col3.metric("Net PNL %", f"{total_pnl:.2f}%")
    col4.metric("Net PNL USDT", f"{total_pnl_usdt:.2f}", delta=f"{total_pnl_usdt:.2f}")
    col5.metric("Open Trades", open_trades)
    col6.metric("Pair With Most Loss", worst_symbol, delta=f"{worst_symbol_pnl:.2f}%")
    col7.metric("Session Runtime", session_runtime)
    capital_display = f"{float(ending_capital):.2f}" if ending_capital is not None else f"{starting_capital:.2f}"
    col8.metric("Session Capital", capital_display, delta=f"Start {starting_capital:.2f}")

    # 3. Performance Visuals
    st.divider()
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Performance by Symbol")
        if not df_closed.empty:
            symbol_stats = df_closed.groupby('Symbol')['PNL_USDT'].sum()
            st.bar_chart(symbol_stats)
        else:
            st.write("No closed trades yet.")

    with c2:
        st.subheader("Win vs Loss Distribution")
        if not df_closed.empty:
            import matplotlib.pyplot as plt

            status_counts = df_closed['Status'].value_counts()

            # Create the figure
            fig, ax = plt.subplots()
            ax.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%',
                   startangle=90, colors=['#2ecc71', '#e74c3c'])
            ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

            # Display it in Streamlit
            st.pyplot(fig)
        else:
            st.write("No data available.")

    # 4. Open Trades View
    st.subheader("🟡 Currently Open Trades")
    if not df_open.empty:
        display_cols = ['Time', 'Symbol', 'Side', 'Entry', 'Target', 'Stop', 'Leverage', 'Qty', 'RiskUSDT', 'Status']
        available_cols = [c for c in display_cols if c in df_open.columns]
        st.dataframe(
            df_open[available_cols].sort_values(by='Time', ascending=False),
            use_container_width=True
        )
    else:
        st.write("No open trades.")

    # 5. Raw Data View
    st.subheader("📋 Raw Trade Data (Recent First)")
    st.dataframe(df.sort_values(by='Time', ascending=False), use_container_width=True)