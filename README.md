# Analisador de Ações B3 — Compra e Venda

Desenvolvido por Pablo Adriano.

Programa de análise estatística para Windows (interface gráfica, 100% offline) que lê CSVs de compra e venda,
monta o ranking das 40 melhores ações e compara configurações (2% x 1%).
**É uma ferramenta de análise sobre dados históricos; não é recomendação de investimento nem garantia de desempenho futuro.**

## Colunas usadas (e somente estas)

`Ativo`, `Qtd Gain`, `Qtd Loss`, `Taxa de Acerto`, `Méd. Volume Leilão`. As demais colunas do CSV são ignoradas.

* **Operações** = Qtd Gain + Qtd Loss (a Taxa de Acerto do arquivo é exatamente Gain ÷ (Gain + Loss)).
* **Méd. Volume Leilão** é *quantidade*, não valor em R$. Aceita `29.869.975` (ponto = milhar), `314513`, `1.234,5`.
  Regra para ponto isolado: grupos de 3 dígitos (`58.448`) são milhar; qualquer outro formato (`572.4`) é decimal.
* Valores ausentes **nunca viram zero**: a linha é rejeitada e contada nos avisos.
* O programa só **lê** os CSVs; nunca altera os originais.

## Regras aprovadas

**Filtros (nesta ordem)**

1. Volume médio **> 80.000** (estritamente maior; 80.000 exato é excluído) — editável na tela.
2. Mínimo de **10 operações** — editável na tela.
3. `Qtd Gain` ≥ 1.

**Pontuação (0 a 100)** entre as ações elegíveis; cada item vira um percentil (0–1):

| Peso | Indicador |
|---|---|
| 70% | Taxa de acerto ajustada pela amostra: limite inferior de Wilson (95%) de `Qtd Gain / Operações` |
| 20% | `Qtd Gain` (percentil; mais é melhor) |
| 10% | `Qtd Loss` (percentil invertido; menos é melhor) |

Desempate: Taxa de Acerto do arquivo (maior primeiro), depois ticker. O volume é só filtro (não pesa na nota).
Se houver menos de 40 elegíveis, mostra todos e informa a quantidade; **nunca completa** com ação reprovada.
Percentil usa posto médio para empates: `posto / n` (Gain e Wilson); para Qtd Loss, `(n − posto_mínimo + 1) / n`.

**Comparativo (aba 2)** — compra com compra, venda com venda.

* Chave: ticker normalizado (sem espaços, maiúsculas). A posição no arquivo não é usada.
* Ticker duplicado no mesmo arquivo: mantém a linha com mais operações e avisa.
* Volume: elegível só se o volume for > 80.000 **nos dois arquivos** (vale o menor); divergência de volume é sinalizada.
* Depois, valem os mesmos filtros de operações em cada arquivo.
* Opcional: limitar aos N melhores de cada ranking (0 = todos os elegíveis).
* Notas calculadas separadamente em cada arquivo. Ordenação: nota média (padrão), pior nota, taxa 2%/1%, menor diferença de taxa, volume, ativo.
* O resumo mostra: presentes nos dois / só em cada um / descartados por volume, por operações e pelo limite de melhores.

## Valor da ação (filtro online, opcional)

Marque **"Filtrar pelo valor da ação (online)"**, informe o **valor mínimo em R$** (padrão 4,00) e cole a **chave da API do
brapi.dev** (https://brapi.dev/dashboard). Desmarcado, o programa continua 100% offline e a coluna fica vazia ("—").

* Fonte: `GET https://brapi.dev/api/v2/stocks/quote?symbols=TICKER`, com `Authorization: Bearer <chave>`; usa `regularMarketPrice`.
  No plano gratuito são 15.000 requisições/mês, 1 ticker por chamada e atraso de ~30 min nas cotações
  (confira os limites atuais no site; podem mudar).
* Regra: **valor ≥ mínimo** passa (R$ 4,00 exato passa). É aplicada junto com volume e operações, **antes da pontuação**.
* Só são consultadas as ações que já passaram em volume, operações e Gain (≈ 190 chamadas por rodada). Compra e venda,
  1% e 2% compartilham as consultas, e o resultado fica em cache por 6 horas (use **Ignorar cache** para forçar atualização).
* **Sem cotação** (ticker não encontrado, preço ausente ou inválido) → ação excluída com o motivo "Sem cotação". Nunca vira zero.
* As consultas são feitas **uma de cada vez** (o brapi limita chamadas simultâneas; excesso gera erro 429). Em caso de 429, o
  programa espera o tempo informado pela API (`Retry-After`) e tenta de novo, até 4 vezes; a barra de status mostra a espera.
  A primeira rodada leva cerca de 1–2 minutos; as seguintes usam o cache.
* Erro de chave (401/403), 429 persistente (cota mensal esgotada ou limite do plano) ou falta de internet **interrompem a análise**
  com mensagem clara (não se monta ranking com preços pela metade). Os preços já obtidos ficam no cache; é só rodar de novo.
* O botão **Testar chave** consulta PETR4 para confirmar que a chave e a conexão funcionam.
* A chave **não é gravada em disco**: fica só na memória enquanto o programa está aberto e precisa ser colada de novo a cada
  vez que abrir. Nunca vai no código nem no `.exe`. (Só se você mesmo definir a variável de ambiente `BRAPI_TOKEN` ela será usada
  quando o campo estiver vazio.) O que fica salvo em `%APPDATA%\AnalisadorAcoes\` são apenas o valor mínimo, o filtro
  ligado/desligado e o cache de preços. Se compartilhou a chave em algum lugar, gere outra no painel do brapi.dev.

## Executar em desenvolvimento

1. Instale o Python 3.10+ (https://www.python.org/downloads/) marcando **Add python.exe to PATH**.
2. Dê dois cliques em `run_dev.bat` (cria o ambiente virtual, instala o `openpyxl` e abre o programa),
   ou manualmente:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python main.py
   ```

## Gerar o executável (.exe)

Dê dois cliques em `build_exe.bat`. Ele instala o PyInstaller e gera **`dist\AnalisadorAcoes.exe`** (arquivo único,
sem console). Esse `.exe` roda em qualquer Windows sem Python instalado. Manualmente:
```
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean --onefile --windowed --name AnalisadorAcoes main.py
```
Se o antivírus reclamar do `.exe` (comum em executáveis PyInstaller sem assinatura), adicione-o às exceções.

## Exportação

* **CSV**: separador `;`, vírgula decimal, UTF-8 com BOM (abre direto no Excel em português). Na aba 1 gera um arquivo por lado
  (`nome_compra.csv`, `nome_venda.csv`).
* **Excel (.xlsx)**: números reais (não texto), filtros, cabeçalho congelado e aba "Resumo" com as contagens.

## Estrutura do código

```
main.py                         ponto de entrada
analisador_acoes/core/          sem interface: csv_loader, ranking, comparison, price_service (brapi), analysis, settings,
                                tables, formatting, exporter, models
analisador_acoes/ui/            tkinter: app, ranking_tab, compare_tab, widgets, theme, tasks (processamento em thread)
tests/                          test_core.py (sintético), test_real_files.py (CSVs reais), ui_smoke.py (interface)
sample_data/                    os 4 CSVs usados na validação
```

## Testes

```
python -m unittest discover -s tests -v          # núcleo, preços (API simulada) e CSVs reais (48 testes)
python tests/ui_smoke.py                          # simula o uso da interface (precisa de tela)
python tests/ui_smoke_price.py                    # idem, com o filtro de valor da ação (API simulada)
```
