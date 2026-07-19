from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import pandas as pd
import os
import numpy as np

app = FastAPI(title="API DataSus - Triângulo Crajubar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. CARREGA O BANCO PRINCIPAL
df = pd.read_csv("data/crajubar_limpo.csv", sep=";")
df['DATA_OBITO'] = pd.to_datetime(df['DATA_OBITO'], dayfirst=True, errors='coerce')
df['ANO_OBITO'] = df['DATA_OBITO'].dt.year
df['MES_OBITO'] = df['DATA_OBITO'].dt.month
df['DIA_OBITO'] = df['DATA_OBITO'].dt.day
df['IDADE_ANOS'] = pd.to_numeric(df['IDADE_ANOS'], errors='coerce')

# 2. CONSTRUÇÃO DO MEGA DICIONÁRIO UNIFICADO (Mantido)
variaveis_sim = [
    {"CATEGORIA": "Município", "CODIGO": "230420", "DESCRICAO": "Crato"},
    {"CATEGORIA": "Município", "CODIGO": "230730", "DESCRICAO": "Juazeiro do Norte"},
    {"CATEGORIA": "Município", "CODIGO": "230190", "DESCRICAO": "Barbalha"},
    {"CATEGORIA": "Sexo", "CODIGO": "1 ou M", "DESCRICAO": "Masculino"},
    {"CATEGORIA": "Sexo", "CODIGO": "2 ou F", "DESCRICAO": "Feminino"},
]
df_mega_dic = pd.DataFrame(variaveis_sim)

arquivos_na_pasta = os.listdir("data/") if os.path.exists("data/") else []
arquivos_cid = [os.path.join("data", f) for f in arquivos_na_pasta if f.upper().startswith("CID") and f.upper().endswith(".CSV")]

dfs_cids = []
for arq in arquivos_cid:
    try:
        tmp_df = pd.read_csv(arq, sep=";", encoding="latin1")
        col_codigo = next((c for c in tmp_df.columns if c.upper() in ['NUMCAP', 'CAT', 'SUBCAT', 'GRUPO', 'CODIGO']), tmp_df.columns[0])
        col_desc = next((c for c in tmp_df.columns if 'DESC' in c.upper()), tmp_df.columns[1] if len(tmp_df.columns) > 1 else tmp_df.columns[0])
        cat_nome = "CID-10 (" + os.path.basename(arq).upper().replace('CID-10-', '').replace('.CSV', '').title() + ")"
        
        tmp_limpo = pd.DataFrame({"CATEGORIA": cat_nome, "CODIGO": tmp_df[col_codigo].astype(str), "DESCRICAO": tmp_df[col_desc].astype(str)})
        dfs_cids.append(tmp_limpo)
    except: pass

if dfs_cids: df_mega_dic = pd.concat([df_mega_dic] + dfs_cids, ignore_index=True)
df_mega_dic = df_mega_dic.fillna("")

# 3. MOTOR DE FILTROS PANDAS
def traduzir_dataframe_para_exportacao(df_sujo):
    df_limpo = df_sujo.copy()
    if 'DATA_OBITO' in df_limpo.columns: df_limpo['DATA_OBITO'] = pd.to_datetime(df_limpo['DATA_OBITO'], errors='coerce').dt.strftime('%d/%m/%Y')
    if 'SEXO' in df_limpo.columns:
        mapa_sexo = {'1': 'Masculino', 'M': 'Masculino', '2': 'Feminino', 'F': 'Feminino', '0': 'Ignorado', 'I': 'Ignorado'}
        df_limpo['SEXO'] = df_limpo['SEXO'].astype(str).map(mapa_sexo).fillna(df_limpo['SEXO'])
    if 'CODMUNRES' in df_limpo.columns and 'MUNICIPIO_RES' not in df_limpo.columns:
        mapa_mun = {'230420': 'Crato', '230730': 'Juazeiro do Norte', '230190': 'Barbalha'}
        df_limpo['MUNICIPIO_RES'] = df_limpo['CODMUNRES'].astype(str).map(mapa_mun).fillna(df_limpo['CODMUNRES'])
    return df_limpo

def aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa):
    df_filtrado = df.copy()
    if municipio == "crato": df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Crato']
    elif municipio == "juazeiro": df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Juazeiro do Norte']
    elif municipio == "barbalha": df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Barbalha']

    if periodo == "pre": df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2017, 2018, 2019])]
    elif periodo == "trans": df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2020, 2021, 2022])]
    elif periodo == "pos": df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2023, 2024, 2025])]

    if faixa_etaria == "jovens": df_filtrado = df_filtrado[df_filtrado['IDADE_ANOS'] <= 29]
    elif faixa_etaria == "adultos": df_filtrado = df_filtrado[(df_filtrado['IDADE_ANOS'] >= 30) & (df_filtrado['IDADE_ANOS'] <= 59)]
    elif faixa_etaria == "idosos": df_filtrado = df_filtrado[df_filtrado['IDADE_ANOS'] >= 60]

    if mes != "todos": df_filtrado = df_filtrado[df_filtrado['MES_OBITO'] == int(mes)]
    if dia_inicio != "todos" and dia_inicio != "": df_filtrado = df_filtrado[df_filtrado['DIA_OBITO'] >= int(dia_inicio)]
    if dia_fim != "todos" and dia_fim != "": df_filtrado = df_filtrado[df_filtrado['DIA_OBITO'] <= int(dia_fim)]

    if sexo != "todos":
        mask_sexo = pd.Series(False, index=df_filtrado.index)
        regex_sexo = r"Masculino|^M$|^1(\.0)?$" if sexo == "Masculino" else r"Feminino|^F$|^2(\.0)?$"
        for col in ['SEXO', 'SEXO_DESC']:
            if col in df_filtrado.columns: mask_sexo = mask_sexo | df_filtrado[col].astype(str).str.contains(regex_sexo, na=False, case=False)
        df_filtrado = df_filtrado[mask_sexo]

    if causa != "todas":
        regex_causa = ""
        if causa == "cardiovascular": regex_causa = r"Circulat|Cardio|^I" 
        elif causa == "respiratoria": regex_causa = r"Respirat|^J"
        elif causa == "gravidez": regex_causa = r"Gravidez|Puerp|Materna|^O" 
        elif causa == "neoplasia": regex_causa = r"Neoplasia|Câncer|Cancer|^C|^D[0-4]"
        mask_causa = pd.Series(False, index=df_filtrado.index)
        for col in ['CID_CAPITULO', 'CAUSABAS', 'DOENCA_DESC']:
            if col in df_filtrado.columns: mask_causa = mask_causa | df_filtrado[col].astype(str).str.contains(regex_causa, na=False, case=False)
        df_filtrado = df_filtrado[mask_causa]

    return df_filtrado

# 4. ROTA DE INTELIGÊNCIA EPIDEMIOLÓGICA (O XEQUE-MATE)
@app.get("/api/resumo-mortalidade")
def get_resumo(municipio: str="todos", periodo: str="todos", faixa_etaria: str="todas", mes: str="todos", dia_inicio: str="todos", dia_fim: str="todos", sexo: str="todos", causa: str="todas"):
    
    # 1. Correção da Linha de Base: Calcula a média de 2017-2019 IGNORANDO o filtro de período atual
    df_base_completa = aplicar_filtros_pandas(municipio, "todos", faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)
    df_2017_2019 = df_base_completa[df_base_completa['ANO_OBITO'].isin([2017, 2018, 2019])]
    media_base = int(len(df_2017_2019) / 3) if len(df_2017_2019) > 0 else 0
    
    # 2. Agora pega os dados reais com TODOS os filtros aplicados
    df_f = aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)
    
    # Gráfico de Linha 
    obitos_por_ano = df_f['ANO_OBITO'].value_counts().sort_index()
    anos = obitos_por_ano.index.astype(int).tolist()
    obitos = obitos_por_ano.tolist()
    
    linha_base = [media_base] * len(anos) # Preenche a linha cinza com a média correta

    # Detetive Estatístico (Z-Score)
    anomalia = {"detectada": False, "ano": 0, "mensagem": ""}
    if len(obitos) >= 3:
        arr_obitos = np.array(obitos)
        media = arr_obitos.mean()
        desvio = arr_obitos.std()
        if desvio > 0:
            max_val = arr_obitos.max()
            ano_max = anos[arr_obitos.argmax()]
            z_score = (max_val - media) / desvio
            if z_score >= 2.0:
                anomalia = {"detectada": True, "ano": ano_max, "mensagem": f"Alerta Estatístico: O ano de {ano_max} registrou um Z-Score de {z_score:.1f} desvios-padrões acima da média. Altíssima probabilidade de surto ou colapso sistêmico."}

    # Relógio Sazonal (Radar)
    meses_totais = df_f['MES_OBITO'].value_counts().reindex(range(1, 13), fill_value=0).sort_index().tolist()

    # Pirâmide Etária Dinâmica
    bins = [0, 9, 19, 29, 39, 49, 59, 69, 79, 120]
    labels_idade = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80+']
    df_f['FAIXA_ETARIA_GRAFICO'] = pd.cut(df_f['IDADE_ANOS'], bins=bins, labels=labels_idade, right=True)
    
    masc = df_f[df_f['SEXO'].astype(str).str.contains(r"Masculino|^M$|^1(\.0)?$", case=False, na=False)]
    fem = df_f[df_f['SEXO'].astype(str).str.contains(r"Feminino|^F$|^2(\.0)?$", case=False, na=False)]
    
    contagem_masc = masc['FAIXA_ETARIA_GRAFICO'].value_counts().reindex(labels_idade, fill_value=0).tolist()
    contagem_fem = fem['FAIXA_ETARIA_GRAFICO'].value_counts().reindex(labels_idade, fill_value=0).tolist()
    
    contagem_masc_negativa = [-x for x in contagem_masc]

    return {
        "linha": {"anos": anos, "obitos": obitos, "baseline": linha_base},
        "anomalia": anomalia,
        "sazonalidade": meses_totais,
        "piramide": {"labels": labels_idade, "masculino": contagem_masc_negativa, "feminino": contagem_fem}
    }

# Demais rotas mantidas
@app.get("/api/dados-brutos")
def get_dados_brutos(municipio: str="todos", periodo: str="todos", faixa_etaria: str="todas", mes: str="todos", dia_inicio: str="todos", dia_fim: str="todos", sexo: str="todos", causa: str="todas", limite: int = 150):
    df_f = traduzir_dataframe_para_exportacao(aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)).fillna("-")
    cols = [c for c in ['DATA_OBITO', 'MUNICIPIO_RES', 'IDADE_ANOS', 'SEXO', 'CID_CAPITULO', 'FLUXO_HOSPITALAR'] if c in df_f.columns]
    return df_f[cols].head(limite).to_dict(orient="records")

@app.get("/api/exportar-csv")
def exportar_csv(municipio: str="todos", periodo: str="todos", faixa_etaria: str="todas", mes: str="todos", dia_inicio: str="todos", dia_fim: str="todos", sexo: str="todos", causa: str="todas", completo: str="false", nome_arquivo: str="DataSus_Exportacao.csv"):
    df_export = df.copy() if completo == "true" else aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)
    return Response(content=traduzir_dataframe_para_exportacao(df_export).to_csv(index=False, sep=";", encoding="utf-8-sig"), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/api/dicionario-global")
def buscar_dicionario(termo: str = ""):
    if not termo: return df_mega_dic.head(50).to_dict(orient="records")
    mask = (df_mega_dic['CODIGO'].str.contains(termo, case=False, na=False) | df_mega_dic['DESCRICAO'].str.contains(termo, case=False, na=False) | df_mega_dic['CATEGORIA'].str.contains(termo, case=False, na=False))
    return df_mega_dic[mask].head(100).to_dict(orient="records")

@app.get("/")
def serve_home(): return FileResponse("frontend/index.html")