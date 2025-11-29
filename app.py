import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.interpolate import griddata
from datetime import datetime
from fpdf import FPDF
import tempfile

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="GeoViz Pro", layout="wide", page_icon="🌍")

# CSS Custom untuk sedikit mempercantik tampilan
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# --- JUDUL UTAMA ---
st.title("🌍 3D Reservoir Visualization")
st.markdown("**Interactive Structural Map & Fluid Contact Modeler**")

# --- 1. INISIALISASI SESSION STATE ---
if 'data_points' not in st.session_state:
    st.session_state['data_points'] = []

# --- 2. SIDEBAR KEREN ---
with st.sidebar:
    st.header("🛠️ Panel Input")
    # --- BAGIAN A: INPUT DATA ---
    st.markdown("### 📍 Input Koordinat")
    
    with st.form(key='input_form', clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            x_val = st.number_input("X (Timur-Barat)", value=0.0, step=10.0)
        with c2:
            y_val = st.number_input("Y (Utara-Selatan)", value=0.0, step=10.0)
        
        z_val = st.number_input("Z (Kedalaman/Depth)", value=1000.0, step=10.0, help="Makin besar angka, makin dalam")
        
        # Tombol Submit dengan tipe Primary (Warna mencolok)
        submit_button = st.form_submit_button(label='➕ Tambah Titik', type="primary")

    if submit_button:
        st.session_state['data_points'].append({'X': x_val, 'Y': y_val, 'Z': z_val})
        st.toast(f"Titik ({x_val}, {y_val}, {z_val}) berhasil disimpan!", icon='✅')

    # --- BAGIAN B: STATUS DATA ---
    df = pd.DataFrame(st.session_state['data_points'])
    
    if not df.empty:
        st.divider()
        st.markdown("### 📊 Status Data")
        
        # Tampilkan Metrics Sederhana
        m1, m2 = st.columns(2)
        m1.metric("Total Titik", len(df))
        m2.metric("Kedalaman Max", f"{df['Z'].max()} m")
        
        # --- BAGIAN C: KONTAK FLUIDA (Hanya muncul jika ada data) ---
        st.divider()
        st.markdown("### 💧 Kontak Fluida")
        
        min_z, max_z = df['Z'].min(), df['Z'].max()
        
        # Input GOC & WOC dengan warna visual
        st.markdown("**:red[Gas-Oil Contact (GOC)]**")
        goc_input = st.number_input("", value=float(min_z + (max_z-min_z)*0.3), key="goc", label_visibility="collapsed")
        
        st.markdown("**:blue[Water-Oil Contact (WOC)]**")
        woc_input = st.number_input("", value=float(min_z + (max_z-min_z)*0.7), key="woc", label_visibility="collapsed")
        
        if goc_input > woc_input:
            st.warning("⚠️ Awas: GOC > WOC!")
    
    st.markdown("---")
        # upload file
    with st.expander("📂 Upload File", expanded=True):
        uploaded_file = st.file_uploader("Upload CSV/Excel (Wajib: X, Y, Z)", type=["csv", "xlsx"])
        
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                else:
                    df_upload = pd.read_excel(uploaded_file)
                    
                # Menampilkan preview 5 baris pertama agar user yakin isinya benar
                st.caption("🔎 Preview data yang kamu upload:")
                st.dataframe(df_upload.head(), use_container_width=True)
                
                # Validasi kolom
                df_upload.columns = [c.upper() for c in df_upload.columns]
                required_cols = {'X', 'Y', 'Z'}
                
                if required_cols.issubset(df_upload.columns):
                    st.success(f"File valid! {len(df_upload)} baris data.")
                    if st.button("📥 Muat Data ke Aplikasi", type="primary"):
                        new_data = df_upload[['X', 'Y', 'Z']].to_dict('records')
                        st.session_state['data_points'].extend(new_data)
                        st.toast(f"Berhasil menambahkan {len(new_data)} titik!", icon='✅')
                        st.rerun() 
                else:
                    st.error(f"Format salah! File harus punya kolom: {required_cols}")
            except Exception as e:
                st.error(f"Error membaca file: {e}")

    # --- BAGIAN D: UTILITAS (Disembunyikan di Expander) ---
    with st.expander("⚙️ Pengaturan Data", expanded=False):
        if st.button("🔄 Reset Semua Data"):
            st.session_state['data_points'] = []
            st.rerun()
        
        if st.button("📂 Load Data Demo"):
            st.session_state['data_points'] = [
                {'X': 100, 'Y': 100, 'Z': 1300}, {'X': 300, 'Y': 100, 'Z': 1300},
                {'X': 100, 'Y': 300, 'Z': 1300}, {'X': 300, 'Y': 300, 'Z': 1300},
                {'X': 200, 'Y': 200, 'Z': 1000}, # Puncak
                {'X': 200, 'Y': 100, 'Z': 1150}, {'X': 200, 'Y': 300, 'Z': 1150},
                {'X': 100, 'Y': 200, 'Z': 1150}, {'X': 300, 'Y': 200, 'Z': 1150},
                {'X': 150, 'Y': 150, 'Z': 1100}, {'X': 250, 'Y': 250, 'Z': 1100},
                {'X': 150, 'Y': 250, 'Z': 1100}, {'X': 250, 'Y': 150, 'Z': 1100}
            ]
            st.rerun()

# --- 3. LOGIC VISUALISASI UTAMA ---
if df.empty:
    st.info("👈 Silakan masukkan data koordinat melalui panel di sebelah kiri.")
    st.image("https://streamlit.io/images/brand/streamlit-mark-color.png", width=100) # Placeholder aja
else:
    # --- PROSES GRIDDATA (Interpolasi) ---
    # Minimal 4 titik untuk kontur yang baik
    if len(df) >= 4:
        df_unique = df.groupby(['X', 'Y'], as_index=False)['Z'].mean()
        grid_x = np.linspace(df['X'].min(), df['X'].max(), 100)
        grid_y = np.linspace(df['Y'].min(), df['Y'].max(), 100)
        grid_x, grid_y = np.meshgrid(grid_x, grid_y)

        try:
            grid_z = griddata((df_unique['X'], df_unique['Y']), df_unique['Z'], (grid_x, grid_y), method='cubic')
        except:
            grid_z = griddata((df_unique['X'], df_unique['Y']), df_unique['Z'], (grid_x, grid_y), method='linear')


        # --- FITUR PERHITUNGAN VOLUME (VOLUMETRICS) ---
        st.markdown("### 📊 Estimasi Volume (Gross Rock Volume)")
        
        # 1. Hitung dimensi sel grid
        x_min, x_max = df['X'].min(), df['X'].max()
        y_min, y_max = df['Y'].min(), df['Y'].max()
        nx, ny = 100, 100
        
        dx = (x_max - x_min) / (nx - 1)
        dy = (y_max - y_min) / (ny - 1)
        cell_area = dx * dy  # Luas per satu kotak grid
        
        # 2. Hitung Volume di atas WOC (Total Reservoir Potensial)
        # Rumus: (WOC - Depth). Jika Depth > WOC (di bawah kontak), tebal = 0.
        thick_above_woc = woc_input - grid_z
        thick_above_woc[thick_above_woc < 0] = 0  # Filter yang di bawah WOC
        vol_total_res = np.nansum(thick_above_woc) * cell_area
        
        # 3. Hitung Volume di atas GOC (Gas Cap)
        thick_above_goc = goc_input - grid_z
        thick_above_goc[thick_above_goc < 0] = 0
        vol_gas_cap = np.nansum(thick_above_goc) * cell_area
        
        # 4. Hitung Volume Oil (Selisih Total - Gas)
        vol_oil_zone = max(0, vol_total_res - vol_gas_cap)

        # 5. Tampilkan Metrics
        col_vol1, col_vol2, col_vol3 = st.columns(3)
        
        # Helper untuk format juta (Million)
        def fmt_vol(v):
            return f"{v/1e6:.2f} Juta m³"

        col_vol1.metric("🔴 Volume Gas Cap", fmt_vol(vol_gas_cap), 
                        help=f"Volume batuan di atas kedalaman {goc_input} m")
        col_vol2.metric("🟢 Volume Oil Zone", fmt_vol(vol_oil_zone), 
                        help="Volume batuan di antara GOC dan WOC")
        col_vol3.metric("🔵 Total Reservoir", fmt_vol(vol_total_res), 
                        help=f"Total volume batuan di atas kedalaman {woc_input} m")
        
        # --- TABS VISUALISASI ---
        tab1, tab2, tab3 = st.tabs(["🗺️ Peta Kontur 2D", "🧊 Model 3D", "📋 Data Mentah"])

        # === TAB 1: 2D ===
        with tab1:
            fig_2d = go.Figure()

            # Layer Kontur
            fig_2d.add_trace(go.Contour(
                z=grid_z, x=np.linspace(df['X'].min(), df['X'].max(), 100),
                y=np.linspace(df['Y'].min(), df['Y'].max(), 100),
                colorscale='Greys', opacity=0.4,
                contours=dict(start=min_z, end=max_z, size=(max_z - min_z)/10, showlabels=True),
                name='Structure'
            ))

            # Layer Titik Fluida
            conditions = [
                (df['Z'] < goc_input),
                (df['Z'] >= goc_input) & (df['Z'] <= woc_input),
                (df['Z'] > woc_input)
            ]
            choices = ['Gas Cap', 'Oil Zone', 'Aquifer']
            colors_map = {'Gas Cap': 'red', 'Oil Zone': 'green', 'Aquifer': 'blue'}
            df['Fluid'] = np.select(conditions, choices, default='Unknown')

            for fluid in choices:
                subset = df[df['Fluid'] == fluid]
                if not subset.empty:
                    fig_2d.add_trace(go.Scatter(
                        x=subset['X'], y=subset['Y'],
                        mode='markers+text', text=subset['Z'].astype(int), textposition="top center",
                        marker=dict(size=12, color=colors_map[fluid], line=dict(width=1, color='black')),
                        name=fluid
                    ))

            fig_2d.update_layout(height=650, margin=dict(l=20, r=20, t=40, b=20),
                                xaxis_title="X Coordinate", yaxis_title="Y Coordinate")
            st.plotly_chart(fig_2d, use_container_width=True)

        # === TAB 2: 3D ===
        with tab2:
            fig_3d = go.Figure()
            
            # Surface Tanah
            fig_3d.add_trace(go.Surface(z=grid_z, x=grid_x, y=grid_y, colorscale='Greys', opacity=0.8, name='Structure'))
            
            # Plane GOC/WOC
            def create_plane(z_lvl, color, name):
                return go.Surface(
                    z=z_lvl * np.ones_like(grid_z), x=grid_x, y=grid_y,
                    colorscale=[[0, color], [1, color]], opacity=0.4, showscale=False, name=name
                )

            fig_3d.add_trace(create_plane(goc_input, 'red', 'GOC'))
            fig_3d.add_trace(create_plane(woc_input, 'blue', 'WOC'))

            # Titik Sumur 3D
            fig_3d.add_trace(go.Scatter3d(
                x=df['X'], y=df['Y'], z=df['Z'], mode='markers',
                marker=dict(size=4, color='black'), name='Wells'
            ))

            fig_3d.update_layout(
                scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Depth', zaxis=dict(autorange="reversed")),
                height=650, margin=dict(l=0, r=0, b=0, t=0)
            )
            st.plotly_chart(fig_3d, use_container_width=True)

        with tab3:
            st.dataframe(df, use_container_width=True)

    else:
        st.warning("⚠️ Data belum cukup untuk membuat kontur. Masukkan minimal 4 titik yang menyebar.")
        st.dataframe(df, use_container_width=True)

    # 2prepare grafik (biar bisa export)    
    # 1. Figure 2D
    fig_2d = go.Figure()
    fig_2d.add_trace(go.Contour(
        z=grid_z, x=np.linspace(df['X'].min(), df['X'].max(), 100),
        y=np.linspace(df['Y'].min(), df['Y'].max(), 100),
        colorscale='Greys', opacity=0.4,
        contours=dict(start=min_z, end=max_z, size=(max_z - min_z)/10, showlabels=True),
        name='Structure'
    ))
        
    # Logic Pewarnaan Titik
    conditions = [
        (df['Z'] < goc_input),
        (df['Z'] >= goc_input) & (df['Z'] <= woc_input),
        (df['Z'] > woc_input)
    ]
    choices = ['Gas Cap', 'Oil Zone', 'Aquifer']
    colors_map = {'Gas Cap': 'red', 'Oil Zone': 'green', 'Aquifer': 'blue'}
    df['Fluid'] = np.select(conditions, choices, default='Unknown')

    for fluid in choices:
        subset = df[df['Fluid'] == fluid]
        if not subset.empty:
            fig_2d.add_trace(go.Scatter(
                x=subset['X'], y=subset['Y'],
                mode='markers+text', text=subset['Z'].astype(int), textposition="top center",
                marker=dict(size=12, color=colors_map[fluid], line=dict(width=1, color='black')),
                name=fluid
            ))
    fig_2d.update_layout(height=600, margin=dict(l=20, r=20, t=40, b=20),
                        xaxis_title="X Coordinate", yaxis_title="Y Coordinate")
    # 2. Figure 3D
    fig_3d = go.Figure()
    fig_3d.add_trace(go.Surface(z=grid_z, x=grid_x, y=grid_y, colorscale='Greys', opacity=0.8, name='Structure'))
    
    def create_plane(z_lvl, color, name):
        return go.Surface(
            z=z_lvl * np.ones_like(grid_z), x=grid_x, y=grid_y,
            colorscale=[[0, color], [1, color]], opacity=0.4, showscale=False, name=name
        )
    fig_3d.add_trace(create_plane(goc_input, 'red', 'GOC'))
    fig_3d.add_trace(create_plane(woc_input, 'blue', 'WOC'))
    fig_3d.add_trace(go.Scatter3d(x=df['X'], y=df['Y'], z=df['Z'], mode='markers',
                                marker=dict(size=4, color='black'), name='Wells'))
    fig_3d.update_layout(scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Depth', zaxis=dict(autorange="reversed")),
                        height=600, margin=dict(l=0, r=0, b=0, t=0))
    # --- E. BAGIAN EKSPOR (DOWNLOAD) ---
    st.markdown("---")
    st.subheader("📂 Ekspor Laporan & Data")
    
    # Persiapan Data untuk 3 Tombol
    
    # 1. Data CSV Grid
    grid_df = pd.DataFrame({'X': grid_x.flatten(), 'Y': grid_y.flatten(), 'Z': grid_z.flatten()}).dropna()
    csv_data = grid_df.to_csv(index=False).encode('utf-8')
    
    # 2. Data TXT Report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt_data = f"""
==================================================
GEOVIZ PRO - LAPORAN SIMULASI RESERVOIR
==================================================
Tanggal Dibuat : {timestamp}
Proyek         : Visualisasi Reservoir 3D
--------------------------------------------------
1. STATISTIK INPUT
--------------------------------------------------
Total Titik        : {len(df)}
Rentang Koordinat  : X ({df['X'].min()} - {df['X'].max()})
                     Y ({df['Y'].min()} - {df['Y'].max()})
Rentang Kedalaman  : {df['Z'].min()} m - {df['Z'].max()} m
--------------------------------------------------
2. MODEL KONTAK FLUIDA
--------------------------------------------------
Kontak Gas-Minyak (GOC) : {goc_input} m
Kontak Air-Minyak (WOC) : {woc_input} m
--------------------------------------------------
3. ESTIMASI VOLUMETRIK (GROSS ROCK VOLUME)
--------------------------------------------------
(*) Vol. Gas Cap              : {vol_gas_cap/1e6:.4f} Juta m³
(*) Vol. Oil Zone             : {vol_oil_zone/1e6:.4f} Juta m³
(*) Total Reservoir           : {vol_total_res/1e6:.4f} Juta m³
--------------------------------------------------
Catatan:
Angka volume di atas adalah estimasi Gross Rock Volume
(GRV) berdasarkan metode interpolasi saat ini.
==================================================
        """.strip()
        
    # 3. Fungsi PDF (dengan Gambar)
    def create_pdf(df, goc, woc, v_gas, v_oil, v_total, fig2d, fig3d):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # --- HALAMAN 1: TEXT SUMMARY ---
        pdf.add_page()
        
        # Header
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "GEOVIZ PRO - LAPORAN LENGKAP", ln=True, align='C')
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, f"Tanggal: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True, align='C')
        pdf.line(10, 30, 200, 30)
        pdf.ln(10)
        
        # Bagian 1: Statistik Input (Ditambahkan)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "1. STATISTIK INPUT", ln=True)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Total Titik Data: {len(df)}", ln=True)
        pdf.cell(0, 8, f"Rentang X: {df['X'].min()} - {df['X'].max()}", ln=True)
        pdf.cell(0, 8, f"Rentang Y: {df['Y'].min()} - {df['Y'].max()}", ln=True)
        pdf.cell(0, 8, f"Rentang Kedalaman (Z): {df['Z'].min()} m - {df['Z'].max()} m", ln=True)
        pdf.ln(5)
        # Bagian 2: Kontak Fluida (Ditambahkan)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "2. MODEL KONTAK FLUIDA", ln=True)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Gas-Oil Contact (GOC): {goc} m", ln=True)
        pdf.cell(0, 8, f"Water-Oil Contact (WOC): {woc} m", ln=True)
        pdf.ln(5)
        
        # Bagian 3: Volumetrik
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "3. ESTIMASI VOLUMETRIK (GRV)", ln=True)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Volume Gas Cap: {v_gas/1e6:.4f} Juta m3", ln=True)
        pdf.cell(0, 8, f"Volume Oil Zone: {v_oil/1e6:.4f} Juta m3", ln=True)
        pdf.cell(0, 8, f"Total Reservoir: {v_total/1e6:.4f} Juta m3", ln=True)
        pdf.ln(5)
        # Catatan
        pdf.set_font("Arial", 'I', 10)
        pdf.multi_cell(0, 6, "Catatan: Angka volume di atas adalah estimasi Gross Rock Volume (GRV) berdasarkan metode interpolasi saat ini.")
        
        # --- HALAMAN 2: SNAPSHOT 2D ---
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "LAMPIRAN A: PETA KONTUR 2D", ln=True, align='C')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig2d.update_layout(plot_bgcolor='white', paper_bgcolor='white')
            fig2d.write_image(tmp.name, width=800, height=600, engine="kaleido")
            pdf.image(tmp.name, x=15, y=40, w=180)
        
        # --- HALAMAN 3: SNAPSHOT 3D ---
        pdf.add_page()
        pdf.cell(0, 10, "LAMPIRAN B: MODEL 3D", ln=True, align='C')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig3d.update_layout(scene=dict(bgcolor='white'), paper_bgcolor='white')
            fig3d.write_image(tmp.name, width=800, height=600, engine="kaleido")
            pdf.image(tmp.name, x=15, y=40, w=180)
        
        return pdf.output(dest='S').encode('latin-1')
    
    # --- LAYOUT 3 KOLOM TOMBOL ---
    col_csv, col_txt, col_pdf = st.columns(3)
    
    with col_csv:
        st.download_button("💾 Download Grid (.csv)", data=csv_data, file_name="grid_data.csv", mime="text/csv")
        
    with col_txt:
        st.download_button("📄 Download Ringkasan (.txt)", data=txt_data, file_name="report.txt", mime="text/plain")
        
    with col_pdf:
        # Tombol Generate PDF (agar tidak berat saat loading awal)
        if st.button("📊 Generate PDF"):
            with st.spinner("Membuat PDF..."):
                try:
                    pdf_bytes = create_pdf(df, goc_input, woc_input, vol_gas_cap, vol_oil_zone, vol_total_res, fig_2d, fig_3d)
                    st.download_button("📥 Klik untuk Download PDF", data=pdf_bytes, file_name="laporan_lengkap.pdf", mime="application/pdf", type="primary")
                except Exception as e:
                    st.error(f"Gagal: {e}")