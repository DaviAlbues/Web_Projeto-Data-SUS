from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pandas as pd

app = FastAPI(title="API DataSuis - Triângulo Crajubar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carrega o banco de dados na memória
df = pd.read_csv("data/crajubar_limpo.csv", sep=";")

# Tratamento de datas
df['DATA_OBITO'] = pd.to_datetime(df['DATA_OBITO'], dayfirst=True, errors='coerce')
df['ANO_OBITO'] = df['DATA_OBITO'].dt.year
df['MES_OBITO'] = df['DATA_OBITO'].dt.month
df['DIA_OBITO'] = df['DATA_OBITO'].dt.day

def aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa):
    df_filtrado = df.copy()

    # 1. Filtro Espacial
    if municipio == "crato":
        df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Crato']
    elif municipio == "juazeiro":
        df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Juazeiro do Norte']
    elif municipio == "barbalha":
        df_filtrado = df_filtrado[df_filtrado['MUNICIPIO_RES'] == 'Barbalha']

    # 2. Filtro Temporal (Anos)
    if periodo == "pre":
        df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2017, 2018, 2019])]
    elif periodo == "trans":
        df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2020, 2021, 2022])]
    elif periodo == "pos":
        df_filtrado = df_filtrado[df_filtrado['ANO_OBITO'].isin([2023, 2024, 2025])]

    # 3. Filtro Demográfico (Idade)
    if faixa_etaria == "jovens":
        df_filtrado = df_filtrado[df_filtrado['IDADE_ANOS'] <= 29]
    elif faixa_etaria == "adultos":
        df_filtrado = df_filtrado[(df_filtrado['IDADE_ANOS'] >= 30) & (df_filtrado['IDADE_ANOS'] <= 59)]
    elif faixa_etaria == "idosos":
        df_filtrado = df_filtrado[df_filtrado['IDADE_ANOS'] >= 60]

    # 4. Filtro Granular (Mês e Faixa de Dias)
    if mes != "todos":
        df_filtrado = df_filtrado[df_filtrado['MES_OBITO'] == int(mes)]
    if dia_inicio != "todos" and dia_inicio != "":
        df_filtrado = df_filtrado[df_filtrado['DIA_OBITO'] >= int(dia_inicio)]
    if dia_fim != "todos" and dia_fim != "":
        df_filtrado = df_filtrado[df_filtrado['DIA_OBITO'] <= int(dia_fim)]

    # 5. Filtro de Sexo "À Prova de Balas" (Busca pela palavra ou pelo código 1 e 2 do DATASUS)
    if sexo != "todos":
        colunas_sexo = [c for c in ['SEXO', 'SEXO_DESC'] if c in df_filtrado.columns]
        if colunas_sexo:
            mask_sexo = pd.Series(False, index=df_filtrado.index)
            if sexo == "Masculino":
                regex_sexo = "Masculino|^M$|^1(\.0)?$" 
            elif sexo == "Feminino":
                regex_sexo = "Feminino|^F$|^2(\.0)?$"
            
            for col in colunas_sexo:
                mask_sexo = mask_sexo | df_filtrado[col].astype(str).str.contains(regex_sexo, na=False, case=False)
            df_filtrado = df_filtrado[mask_sexo]

    # 6. Filtro Clínico "À Prova de Balas" (Busca pelas palavras ou pelas letras do CID-10)
    if causa != "todas":
        # Procura em qualquer coluna de doença que exista no seu CSV
        colunas_busca = [c for c in ['CID_CAPITULO', 'CAUSABAS', 'DOENCA_DESC'] if c in df_filtrado.columns]
        if colunas_busca:
            if causa == "cardiovascular":
                regex_causa = "Circulat|Cardio|^I" # Códigos I (ex: I500 - Infarto)
            elif causa == "respiratoria":
                regex_causa = "Respirat|^J" # Códigos J (ex: J12 - Pneumonia/COVID)
            elif causa == "gravidez":
                regex_causa = "Gravidez|Puerp|Materna|^O" # Códigos O (Mortalidade Materna)
            elif causa == "neoplasia":
                regex_causa = "Neoplasia|Câncer|Cancer|^C|^D[0-4]" # Códigos C e D (Tumores)
            
            mask_causa = pd.Series(False, index=df_filtrado.index)
            for col in colunas_busca:
                mask_causa = mask_causa | df_filtrado[col].astype(str).str.contains(regex_causa, na=False, case=False)
            df_filtrado = df_filtrado[mask_causa]

    return df_filtrado

@app.get("/api/resumo-mortalidade")
def get_resumo(municipio: str = "todos", periodo: str = "todos", faixa_etaria: str = "todas", mes: str = "todos", dia_inicio: str = "todos", dia_fim: str = "todos", sexo: str = "todos", causa: str = "todas"):
    df_filtrado = aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)
    
    obitos_por_ano = df_filtrado['ANO_OBITO'].value_counts().sort_index().to_dict()
    anos_completos = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    valores = [obitos_por_ano.get(ano, 0) for ano in anos_completos]

    return {"anos": anos_completos, "obitos": valores}

@app.get("/api/dados-brutos")
def get_dados_brutos(municipio: str = "todos", periodo: str = "todos", faixa_etaria: str = "todas", mes: str = "todos", dia_inicio: str = "todos", dia_fim: str = "todos", sexo: str = "todos", causa: str = "todas", limite: int = 150):
    df_filtrado = aplicar_filtros_pandas(municipio, periodo, faixa_etaria, mes, dia_inicio, dia_fim, sexo, causa)
    
    df_filtrado['DATA_OBITO'] = df_filtrado['DATA_OBITO'].dt.strftime('%d/%m/%Y')
    df_filtrado = df_filtrado.fillna("-")
    
    colunas_tabela = ['DATA_OBITO', 'MUNICIPIO_RES', 'IDADE_ANOS', 'SEXO', 'CID_CAPITULO', 'FLUXO_HOSPITALAR']
    colunas_existentes = [col for col in colunas_tabela if col in df_filtrado.columns]
    
    amostra = df_filtrado[colunas_existentes].head(limite).to_dict(orient="records")
    return amostra

@app.get("/")
def serve_home():
    """Entrega o site (HTML) quando o usuário acessa a raiz do link"""
    return FileResponse("frontend/index.html")