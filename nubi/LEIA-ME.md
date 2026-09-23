# nubi — Explorador de anúncios

Transforma os exports CSV do Nubimetrics em planilhas Excel de acompanhamento,
uma por marca, com histórico acumulado entre períodos.

## Instalação (uma vez só)

Precisa de Python 3.9 ou mais novo. No terminal:

```
pip install pandas openpyxl
```

## Como usar

1. Coloque os CSVs na pasta `entrada/`.
2. Rode:
   ```
   python nubi.py
   ```
3. As planilhas saem em `saida/`.

Pode deixar os CSVs antigos na pasta `entrada/`: arquivo já importado é
reconhecido e pulado, sem duplicar nada.

## Marca e período de cada arquivo

O CSV não diz de qual marca nem de qual período ele é. Existem três formas de informar:

**1. Pelo nome do arquivo (recomendado).** Renomeie assim:

```
MARCA__AAAA-MM-DD_AAAA-MM-DD.csv
```

São **dois** underlines depois da marca. Underline simples dentro da marca vira espaço.
Exemplos:

```
ARMAF__2026-08-01_2026-09-16.csv
CUBA_PARIS__2026-08-01_2026-09-16.csv
JACQUES_BOGART__2026-09-17_2026-09-30.csv
```

**2. Pela linha de comando**, para todos os arquivos cujo nome não segue o padrão:

```
python nubi.py --marca MONTBLANC --inicio 2026-08-01 --fim 2026-09-16
```

**3. Respondendo no terminal.** Se nada acima foi informado, o programa pergunta a
marca, sugerindo a que aparece na coluna Marca do CSV, e as datas.

Se o programa rodar agendado, sem ninguém no terminal, o arquivo sem marca ou
período é pulado com um aviso e os demais seguem normalmente.

Importar de novo a mesma marca e o mesmo período com outro arquivo, como um
export refeito, **substitui** a importação anterior.

## Como os anúncios viram referências

O mesmo perfume aparece em dezenas de anúncios com títulos diferentes. O programa
junta esses anúncios em referências reais (`Marca Linha Tipo Volume`):

1. **Lê o título**: linha de produto (pelo `marcas.json`), volume (`100 ml`) e
   tipo (EDT, EDP, EDC, Body Splash, Deo, Banho, Kit).
2. **Confirma pelo GTIN**: todos os anúncios com o mesmo GTIN são o mesmo produto.
   O título do anúncio que mais vendeu corrige os títulos cortados ou errados.
3. **Preenche o que faltou**: um anúncio sem volume ou sem tipo no título copia o
   que mais vende na mesma linha.

Antes disso, o GTIN é cruzado com a coluna **Marca**:
- Anúncios de outra marca que vieram no export (contratipos como J. Serrano, ou
  cadastro errado) viram a referência `Outra marca: ...`.
- Um vendedor que pôs o nome da loja na coluna Marca, mas usa o GTIN da marca,
  continua contando como da marca.
- Produtos de outras categorias (canetas, cintos…) viram `... (não perfume)`.

Tudo continua somando no total, só que separado.

## marcas.json

Lista, por marca, os textos a procurar no título e o nome que aparece no relatório:

```json
"ARMAF": {"linhas": [
  ["club de nuit intense man", "Club de Nuit Intense Man"],
  ["club de nuit", "Club de Nuit Intense Man"]
]}
```

- Escreva o texto de busca em minúsculas e sem acento.
- Coloque os nomes compostos **antes** dos curtos.
- Duas chaves podem apontar para o mesmo nome. É assim que se resolve apelido.
- **Marca nova**: se a marca não está no arquivo, o programa detecta as linhas
  sozinho na primeira importação, grava aqui e mostra a lista no terminal.
  Revise essa lista, porque linhas pequenas (menos de 1,5% do volume) não entram.
  Depois de editar, é só rodar de novo: o histórico inteiro é reprocessado com a
  configuração nova.

## O que tem em cada planilha

Arquivo `saida/<marca>-explorador-de-anuncios.xlsx`:

| Aba | O que mostra |
|---|---|
| **Resumo** | Indicadores do período (unidades, faturamento, giro/dia, projeções, vendedores, % catálogo, % FULL) e concentração Top 1/3/5/10/20. |
| **Evolução** | Só aparece a partir do 2º período da marca. Compara o período atual com o anterior, por referência, **sempre por dia**: acelerando, perdendo giro, estável, novo, sumiu. |
| **Produtos** | Uma linha por referência, com curva ABC, giro e disputa (unidades por anúncio). |
| **GTINs** | Vendas por GTIN. No rodapé, quantas unidades ficaram sem GTIN válido: é a medida de quão sujo está o cadastro da marca. |
| **Vendedores** | Ranking com código V01, V02… Em verde, quem tem 5% ou mais do mercado. |
| **Preços** | Mínimo, quartis, mediana, máximo, amplitude e unidades vendidas abaixo de 80% da mediana. |
| **Anúncios** | A base limpa, anúncio por anúncio, com o produto consolidado ao lado. É aqui que se confere quando um número parecer estranho. |

Arquivo `saida/painel-geral.xlsx`: todas as marcas lado a lado, sempre no período
mais recente de cada uma.

Importante:
- Os números são do **mercado inteiro** (todos os vendedores), não da sua loja.
- O faturamento vem arredondado em faixas pela plataforma, então preços médios
  calculados por faturamento ÷ unidades são aproximados.
- As colunas derivadas são fórmulas do Excel. Se você corrigir um produto na aba
  Anúncios, as outras abas se atualizam.

## Pastas

```
nubi.py        o programa
marcas.json    linhas de produto por marca
entrada/       coloque os CSVs aqui
saida/         planilhas geradas
dados/base.db  histórico (criado sozinho; não apague se quiser a aba Evolução)
```

Se algo der errado, o programa mostra uma frase explicando o problema. O
detalhe técnico fica em `dados/erro.log`.
