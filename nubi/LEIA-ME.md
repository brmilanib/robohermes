# nubi — Explorador de anúncios

Transforma os exports CSV do Nubimetrics em planilhas Excel de acompanhamento,
uma por marca, com histórico acumulado entre períodos.

## Versão web (no navegador)

Acesse **https://nubi-explorador-vb-financeiro.vercel.app** e entre com o seu e-mail.
Você recebe um link de acesso no e-mail. Na página dá para:

- **Importar CSV**: arraste um ou mais exports. Marca e período vêm do nome do arquivo
  (padrão abaixo) ou você preenche no formulário.
- Ver o **painel geral** e, em cada marca, as abas Oportunidades, Evolução,
  Histórico, Produtos, Preços, Vendedores, GTINs, Dúvidas e Anúncios. Todas têm
  filtros por coluna, busca e ordenação.
- **Pesquisar GTINs em dúvida** e **corrigir à mão** o nome oficial de um GTIN (aba Dúvidas).
- Editar as **linhas de produto** da marca (aba Configuração). O histórico é
  reprocessado na hora.
- Apagar um período importado por engano (aba Períodos).
- **Baixar o Excel** completo, igual ao gerado no computador.

Como funciona por trás:
- Os dados ficam no **Supabase** (projeto `nubi`).
- A página e o motor em Python rodam na **Vercel** (projeto `nubi-explorador`).
- O código fica neste repositório. Cada push na branch publicada gera uma nova versão.
- Só os e-mails cadastrados na tabela `acesso` do Supabase veem os dados. Para
  liberar alguém, adicione o e-mail dessa pessoa lá (Table Editor → acesso → Insert row).
- Para usar a base Cosmos na pesquisa de GTIN, cadastre o token na variável de
  ambiente `NUBI_COSMOS_TOKEN` do projeto na Vercel.

A versão de computador continua funcionando igual, com os dados locais em `dados/base.db`.

## Instalação no computador (uma vez só)

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

**Monitoramento diário:** importe um CSV por dia, por exemplo
`ARMAF__2026-09-23_2026-09-23.csv`. A aba **Histórico** vira a série diária de
cada produto e a aba **Oportunidades** mostra o que acelerou.

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

## Quando o agrupamento está em dúvida: pesquisar o GTIN

Às vezes os anúncios do mesmo GTIN não concordam sobre o produto: um diz 75 ml e
outro 80 ml, um diz Individuel e outro Individuelle. Às vezes a linha nem é
reconhecida. Esses GTINs aparecem na aba **Dúvidas**, e o programa sempre mostra
no fim da execução o comando que resolve:

```
python nubi.py --pesquisar-gtin
```

O comando busca a especificação oficial de cada GTIN em dúvida, começando pelos
que mais vendem, nas bases públicas Open Beauty Facts e UPCitemdb. O resultado é
gravado em `gtins.json` e passa a valer mais que qualquer título de anúncio: define
linha, volume, tipo, gênero e até a **marca**. Se a base disser que o GTIN é de
outra marca, os anúncios desse GTIN vão para "Outra marca".

- Por padrão pesquisa até 40 por vez. Para mudar: `--limite 100`.
- Para pesquisar GTINs específicos: `python nubi.py --gtin 3386460101035 3386460028462`.
- Um GTIN não encontrado fica marcado, e a aba Dúvidas tem um link "pesquisar" que
  abre o Google com ele. Achou? Escreva à mão no `gtins.json`:
  ```json
  "3386460028462": {"nome": "Montblanc Starwalker Eau de Toilette 75 ml", "marca": "Montblanc"}
  ```
  Depois rode `python nubi.py` de novo.
- **Base brasileira (opcional, melhor para GTIN 789…):** crie uma conta grátis no
  Cosmos (cosmos.bluesoft.com.br), copie o token e salve num arquivo
  `cosmos-token.txt` ao lado do `nubi.py`. O Cosmos passa a ser consultado primeiro.
- O nome pesquisado é lido com a mesma lista do `marcas.json`. Se a pesquisa
  trouxer uma linha que não está na lista (ex.: "Legend Blue"), acrescente essa linha
  ao `marcas.json`.

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
| **Resumo** | Indicadores do período (unidades, faturamento, giro/dia, projeções, vendedores, % catálogo, % FULL), concentração Top 1/3/5/10/20 e as 5 melhores oportunidades. |
| **Oportunidades** | Onde entrar. Cada produto da marca recebe uma **nota de 0 a 100** e **sinais**: pouca concorrência, FULL livre, catálogo pouco disputado, líder domina, acelerando, perdendo giro, novo, preço disperso. A demanda multiplica a nota, então produto sem venda não aparece bem colocado. |
| **Evolução** | Só aparece a partir do 2º período da marca. Compara o período atual com o anterior, por referência, **sempre por dia**: acelerando, perdendo giro, estável, novo, sumiu. |
| **Histórico** | Giro/dia de cada produto em cada período importado (até os 30 últimos), comparando o último com a média. |
| **Produtos** | Uma linha por referência, com curva ABC, giro, disputa (unidades por anúncio) e a confiança do agrupamento. |
| **GTINs** | Vendas por GTIN, a especificação pesquisada e um link para pesquisar. No rodapé, quantas unidades ficaram sem GTIN válido: é a medida de quão sujo está o cadastro da marca. |
| **Dúvidas** | GTINs cujos anúncios não concordam sobre o produto, com os títulos conflitantes e o resultado da pesquisa. |
| **Vendedores** | Ranking com código V01, V02… Em verde, quem tem 5% ou mais do mercado. |
| **Preços** | Mínimo, quartis, mediana, máximo, amplitude e unidades vendidas abaixo de 80% da mediana. |
| **Anúncios** | A base limpa, anúncio por anúncio, com o produto consolidado ao lado. É aqui que se confere quando um número parecer estranho. |

### Categorias para filtrar

As abas Produtos, Oportunidades, Preços, Evolução e Anúncios têm colunas de filtro
(use a setinha do cabeçalho):

- **Categoria**: Perfume, Kit, Body Splash, Desodorante, Banho, Outra marca, Não perfume.
- **Linha**, **Tipo** (EDT/EDP/EDC…) e **Volume**.
- **Tamanho**: Miniatura (até 30 ml), Pequeno (31–60), Padrão (61–125), Grande (126+).
- **Gênero**: Masculino, Feminino ou Unissex, lido do título e confirmado pelo GTIN.
- **Faixa de preço**: até R$ 99, R$ 100–199, R$ 200–299, R$ 300–499, R$ 500+.
- **Curva ABC** e **Confiança do agrupamento**. A confiança diz como o anúncio foi
  agrupado: pesquisado pelo GTIN, confirmado pelo GTIN, só pelo título, ou em dúvida.

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
gtins.json     especificações pesquisadas por GTIN (criado sozinho; pode editar)
entrada/       coloque os CSVs aqui
saida/         planilhas geradas
dados/base.db  histórico (criado sozinho; não apague se quiser a aba Evolução)
```

Se algo der errado, o programa mostra uma frase explicando o problema. O
detalhe técnico fica em `dados/erro.log`.
