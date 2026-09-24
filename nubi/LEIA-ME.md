# nubi — Explorador de anúncios

Transforma os exports CSV do Nubimetrics em planilhas Excel de acompanhamento,
uma por marca, com histórico acumulado entre períodos.

## Versão web (no navegador)

Acesse **https://nubi-explorador.vercel.app** e entre com e-mail e senha. Na página dá para:

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

### Agente de GTIN automático

Os GTINs em dúvida (aba Dúvidas) são pesquisados sozinhos, sem precisar apertar botão:

- **Depois de cada importação**, para a marca importada (até 2 minutos).
- **Enquanto a página está aberta**, a cada 10 minutos (1 hora quando a fila está vazia).
- **Uma vez por dia na nuvem** (Vercel Cron, 6h de Brasília), mesmo com a página fechada.

Ele pesquisa dos GTINs que mais vendem para os que menos vendem e grava o nome oficial.
Depois reagrupa os produtos da marca. O que não existir em nenhuma base fica na aba Dúvidas
para você corrigir à mão; esse GTIN é pesquisado de novo depois de 30 dias. O menu lateral e
a aba Dúvidas mostram a última rodada. O botão **Rodar o agente agora** faz uma rodada na hora.

Como a rodada diária roda sem ninguém logado, o agente tem um login próprio
(`agente.nubi@example.com`, liberado na tabela `acesso`, com o mesmo acesso que o seu). As
variáveis `NUBI_AGENTE_EMAIL`, `NUBI_AGENTE_SENHA` e `CRON_SECRET` ficam no projeto da
Vercel. Cada rodada fica registrada na tabela `agente_execucoes`.

### Ranking mensal de marcas (menu lateral)

A segunda função do menu lateral lê o relatório **MARCAS** do Nubimetrics do mês
fechado. É o arquivo `.xlsx` com uma linha por marca: posição, variação, vendas em $,
quantidade, tendência, catálogo, vendedores, saturação e ranking de demanda. Esse
relatório não traz produtos.

- **Importar relatório do mês**: categoria e mês vêm do nome do arquivo
  (`MARCAS-MLB1246-MLB6284-2026-08-01_1.xlsx` → Perfumes, agosto de 2026).
- A página mostra:
  - os indicadores do mês: vendas, unidades, ticket médio, concentração, tendência e saturação;
  - **Onde vale olhar**: nota de oportunidade por marca. Pesam crescimento, pouca
    saturação, poucos vendedores para o volume e subida no ranking. O tamanho só conta
    até o nível das 25% maiores;
  - as **maiores marcas** e o ranking completo com filtros;
  - ticket médio, vendas por vendedor e share em cada marca.
- A partir do 2º mês da mesma categoria aparecem a variação de vendas e unidades, as
  marcas que entraram e as que saíram do ranking.
- Clicar numa marca abre o histórico dela mês a mês. Se a marca também está no
  Explorador, aparece o atalho para os anúncios dela.

#### B.I. · todos os meses

O botão **📊 B.I.** (ou o item embaixo da categoria no menu) junta todos os meses importados
da categoria. O filtro **De / até** limita o período e vale para a tela inteira.

- **Indicadores**: vendas do último mês, crescimento no período (e a média ao mês),
  vendas somadas, ticket médio, concentração top 5, marcas presentes em todos os
  meses, marcas novas por mês e melhor/pior mês.
- **Gráficos**:
  - vendas do mercado por mês;
  - share e posição no ranking das 8 maiores marcas;
  - quem mais ganhou e perdeu vendas (último mês, 3 meses ou período);
  - demanda × concorrência (crescimento das vendas × crescimento dos vendedores);
  - mapa de calor das 25 maiores (posição e variação mês a mês);
  - ticket médio, concentração e tendência das marcas por mês.
  Passe o mouse para ver os números. Clique numa marca para ver o histórico dela.
- **Para acompanhar**: as 10 marcas com a maior nota B.I. A nota soma o crescimento em
  3 meses, a consistência (meses em alta), a subida no ranking, a saturação e as vendas
  crescendo mais que os vendedores.
- **Status** de cada marca: Subindo forte, Crescimento consistente, Estável, Instável, Em
  queda, Nova ou Saiu do ranking.
- **Entradas e saídas do top 100** (a partir do 2º mês):
  - gráfico com quantas marcas entraram e saíram do ranking em cada mês;
  - **🚀 Vindo de baixo**: marcas que entraram, continuam no ranking e ganharam
    posições ou share desde a entrada;
  - **📉 Saindo do hype**: marcas que saíram e não voltaram, ordenadas pela queda
    desde o pico de faturamento;
  - duas tabelas por mês (filtro Mês):
    - **Entraram**: faturamento e posição na entrada, onde estão agora e o pico;
    - **Saíram**: último faturamento e posição, pico, mês do pico, meses no ranking e se voltaram.
  - "O que aconteceu" resume cada caso: Ficou e cresceu, Ficou, Ficou mas caindo,
    Entrou e saiu, Entrou agora; Perdeu fôlego, Passou rápido, Voltou depois, Saiu.
  - Crescer aqui olha o share e a posição, não só o R$. Assim não confunde a marca
    crescendo com o mercado inteiro crescendo.
- O relatório traz só as maiores marcas de cada mês. Se uma marca some num mês, ela
  saiu do ranking; não quer dizer que vendeu zero. Por isso as variações só comparam
  meses em que a marca aparece.

### Vendedores monitorados (menu lateral)

A terceira função lê o export de anúncios de um vendedor que você segue no Nubimetrics,
mês fechado (.xlsx): título, marca, vendas, unidades, preço, FULL, catálogo, tipo de
publicação, GTIN...

- **Importar vendedor**: o nome do arquivo vira o nome do vendedor
  (`AUMA_PERFUMARIA_P2.xlsx` → AUMA PERFUMARIA P2, o mesmo nome da coluna Vendedor do
  Explorador). O mês fechado é escolhido na importação. Use sempre o mesmo nome para os
  meses do vendedor se juntarem. Reimportar o mesmo vendedor e mês substitui o anterior.
- **Página do vendedor**:
  - indicadores: vendas, unidades, ticket, anúncios, marcas e % em FULL, catálogo e
    Premium, com a variação contra o mês anterior;
  - vendas mês a mês;
  - marcas que ele começou a vender e marcas que ele parou de vender;
  - abas Marcas, Produtos (agrupados por GTIN) e Anúncios.
- **Cruzamento com o Ranking de marcas** (precisa do relatório MARCAS do mesmo mês):
  - **% do mercado**: quanto das vendas de cada marca passa por ele;
  - **Onde ele é forte**: as marcas em que ele tem a maior fatia;
  - **Oportunidades**: marcas em alta no B.I. em que ele tem menos de 1% das vendas;
  - **Riscos**: marcas em queda que pesam 2% ou mais nas vendas dele;
  - **Vindo de baixo que ele não vende**: marcas que entraram no ranking e ficaram ou cresceram.
- **Cruzamento com o Explorador**: para os GTINs das marcas monitoradas, o preço médio do
  mercado, o preço dele contra esse preço, quantos vendedores tem o GTIN e a posição e a
  fatia dele. O período do Explorador pode ser diferente do mês do vendedor.
- **Comparar vendedores**:
  - vendas no mês de cada vendedor seguido;
  - como cada um vende (ticket, FULL, catálogo, Premium);
  - uma matriz com as 25 maiores marcas e a fatia de cada vendedor no mercado da marca.

### Nomes de marcas (menu lateral, 🔗)

A mesma marca aparece escrita de jeitos diferentes nos arquivos dos vendedores (YSL e
Yves Saint Laurent, Thierry Mugler e Mugler, erros como "David Beckmam"). Nessa tela:

- **Sugestões**: pares que parecem a mesma marca. Os motivos são sigla, grafia parecida
  ou nome contido no outro. O destino é o nome do ranking do Nubimetrics, ou o que mais
  vende. "Juntar" confirma o par; "Não é a mesma" esconde a sugestão.
- **Juntar à mão**: escreva como a marca aparece no arquivo e o nome oficial.

A junção vale na hora para o Ranking, o B.I. e os Vendedores, inclusive nos dados já
importados. Os arquivos continuam guardados com o nome original, então dá para desfazer.

### Nomes de vendedores (identidade do vendedor)

O Nubimetrics mostra um nome aleatório para vendedor sem apelido (ex.:
BANTENG.PRETO.DEMONSTRATIVO) e esse nome pode mudar. Por isso o nome não é a identidade do
vendedor no nubi:

1. **Hash do Nubimetrics** (chave principal): o coletor automático manda o hash de cada
   vendedor (128 caracteres, fixo por vendedor). Mesmo hash é o mesmo vendedor. Se um
   vendedor com nome aleatório ganha apelido, o histórico dele passa para o apelido sozinho.
2. **Impressão digital dos anúncios** (reserva, para importação manual ou se o hash
   mudar): compara os ~200 itens que mais vendem (GTIN, senão SKU, senão título + marca)
   com os vendedores que ainda não têm aquele mês.
   - Junta sozinho só quando itens em comum ≥ 60%, faturamento parecido (≥ 50%), mix de
     marcas parecido (≥ 80%) e tamanho de catálogo parecido (≥ 60%). Lojas de perfume
     vendem muitos GTINs iguais, por isso itens sozinhos não bastam.
   - Entre 35% e 60% de itens em comum (ou se faltar algum dos outros critérios), importa
     com o nome do arquivo e deixa para você conferir.

A tela **🔗 Nomes de vendedores** (menu Vendedores) mostra:
- o que está **para conferir**, com os botões "É o mesmo" e "São diferentes";
- os vendedores com os outros nomes que já usaram e o hash;
- o histórico das decisões, com "desfazer";
- a opção de **juntar à mão**.

### Coletor automático do Nubimetrics (Mac mini)

Um programa no Mac mini abre o Nubimetrics com o seu login já salvo, baixa os relatórios
e manda para o nubi sozinho. O Explorador de anúncios continua manual.

**Instalar** (uma vez, no Terminal do Mac mini):

```
curl -fsSL https://nubi-explorador.vercel.app/coletor/instalar.sh | bash
```

O instalador:
1. prepara o Python e o navegador do coletor em `~/.nubi-coletor`;
2. agenda a coleta para todo dia às 7h00. Para mudar depois: `~/.nubi-coletor/coletor agendar 8 15`
   (8h15);
3. pede o login do **nubi** (guardado no Chaveiro do Mac), usado para enviar os arquivos;
4. abre uma janela do navegador para você entrar no **Nubimetrics**. O login fica salvo no
   perfil do coletor, e a senha do Nubimetrics não é gravada.

**O que ele faz todo dia** (`coletor diario`, às 7h00). O Nubimetrics libera os dados com 2
dias de atraso, então no dia 23 os dados vão até o dia 21. Ele só baixa o que ainda falta no
nubi. Cada arquivo sai com o nome que o Nubimetrics dá, numa pasta por mês, e vai junto um
`manifest.json` com o hash de cada vendedor.
- **Histórico desde janeiro/2026** (`"desde"` no `config.json`): para cada um dos vendedores
  do grupo "perfumes", baixa cada mês fechado que falta. Na primeira vez são 16 vendedores ×
  9 meses, então leva algumas horas; nas vezes seguintes, só o que mudou.
- **Mês atual até o último dia liberado**: todo dia o mês em andamento é baixado de novo e
  aparece no nubi como "setembro de 2026 (parcial até 21/09)". Quando o último dia do mês
  é liberado (ex.: 02/10 para setembro), o mês fecha e passa a ser o completo.
- O relatório **MARCAS** de cada mês fechado que ainda não está no nubi.
- Vendedor novo no grupo entra sozinho, com o histórico desde janeiro.
- Cada coleta fica registrada no nubi (menu lateral e página Vendedores). Se falhar,
  aparece como "falhou" e o Mac mostra uma notificação.
- Meses passados usam um período personalizado. Se a tela do Nubimetrics ignorar o período
  que vai no endereço, o coletor escolhe as datas no calendário (dd/mm/aaaa e APLICAR).

**Comandos úteis** (no Terminal):

| Comando | Para quê |
|---|---|
| `~/.nubi-coletor/coletor diario` | roda a coleta agora |
| `~/.nubi-coletor/coletor status` | últimas coletas |
| `~/.nubi-coletor/coletor entrar` | refazer o login do Nubimetrics (se a sessão expirar). Depois do login, ele testa se consegue entrar sozinho sem janela; se o Nubimetrics não aceitar, passa a coletar com a janela aberta |
| `~/.nubi-coletor/coletor atualizar` | baixa a versão mais nova do coletor |
| `... --ver` | em qualquer coleta, mostra a janela do navegador para acompanhar |
| `~/.nubi-coletor/coletor vendedores --mes 2026-07` | baixar um mês específico |
| `~/.nubi-coletor/coletor marcas --mes 2026-07` | baixar o MARCAS de um mês específico |
| `~/.nubi-coletor/coletor vendedores --parcial` | só o mês atual, até o último dia liberado |
| `~/.nubi-coletor/coletor agendar 7 0` | muda o horário da coleta diária |

**Cuidados:**
- O Mac precisa estar ligado e com o seu usuário logado no horário. Para o Mac acordar
  sozinho: `sudo pmset repeat wakeorpoweron MTWRFSU 06:55:00`.
- Vendedores sem apelido aparecem com nome aleatório no Nubimetrics (ex.:
  BANTENG.PRETO.DEMONSTRATIVO). O coletor avisa (no log, no nubi e na tela do Mac) para
  você dar um apelido a eles no Nubimetrics (ícone de lápis). O histórico não se perde,
  porque a identidade é o hash.
- O coletor anota o hash de cada vendedor por dia. Se um apelido aparecer com hash
  diferente do anterior, ele avisa: é o sinal de que o hash não é estável, e aí vale a
  impressão digital dos anúncios.
- Para não baixar o mês atual todo dia, use `"mes_atual": false` em
  `~/.nubi-coletor/config.json`. Para mudar o atraso de liberação, use `"atraso_dias"`.

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

**Mesmo GTIN = mesmo produto.** Se os anúncios do mesmo GTIN têm títulos diferentes
(um diz 75 ml e outro 80 ml, um diz Individuel e outro Individuelle), isso não é dúvida:
o grupo inteiro fica com o que diz o título do anúncio que mais vende.

Se a linha do produto não está nas linhas configuradas da marca, ela é lida do próprio
título: o que sobra tirando marca, tipo, volume e palavras de anúncio. Por exemplo,
"Perfume Carolina Herrera 212 Men Masculino Edt 200ml" vira a linha "212 Men". Esses
anúncios aparecem com a confiança "Linha pelo título (GTIN)".

Só fica em dúvida o GTIN em que nenhum título diz a linha (ex.: "Perfume Carolina Herrera
Eau de Toilette 100ml"). Esses GTINs aparecem na aba **Dúvidas**, e o programa sempre
mostra no fim da execução o comando que resolve:

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
| **Dúvidas** | GTINs em que nenhum título diz a linha do produto, com os títulos e o resultado da pesquisa. |
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

## B.I. dos vendedores e alertas de estoque

- **Visão do ano** (`#/vendedores/NOME`): vendas e ritmo (R$/dia) por mês, projeção do mês atual, fatia das 8 maiores
  marcas, produtos subindo/caindo/novos e a tabela de produtos com o ritmo mês a mês. **Mês a mês** (`#/vendedores/NOME/AAAA-MM`)
  abre no último mês fechado; no mês parcial as variações são pelo ritmo por dia (não pelo total).
- **Produto** (clique em qualquer produto): vendas por dia no mês atual (diferença entre as fotos diárias do coletor,
  tabela `vend_produto_dia`), unidades por mês e quem mais vende entre os monitorados.
- **Alertas de estoque** (`#/alertas` e `#/vendedores/NOME/alertas`): produto que vendia ≥ 0,5 un/dia no mês anterior e agora
  está com todos os anúncios pausados (sem estoque no Mercado Livre), parou de vender há dias, sumiu ou caiu abaixo de 35% do ritmo.
  O número no menu conta os produtos sem estoque/parados em algum concorrente. Regras em `vend_bi.py`.
- O export do Nubimetrics só traz anúncios com venda e o estado ATUAL do anúncio; as unidades são estimativas
  (arredondadas de 10 em 10 nos produtos grandes).

## Categorias de marca (Ranking → 🏷️ Categorias)

Cada marca do ranking MARCAS entra numa categoria: **Alta perfumaria**, **Designer** (grife de moda), **Nicho**, **Árabe**, **Importados low ticket** (importada que só faz perfume, preço em conta), **Nacional** (perfumaria brasileira) ou **Outros** (não é marca de perfume).
A classificação automática vem da lista em `categorias.py`; o que você escolher na tela fica na tabela `marca_categorias` e vale
para todos os meses. A tela mostra vendas e fatia de cada categoria mês a mês, o crescimento e as maiores marcas de cada uma.

## IA (ChatGPT ou Claude)

Com `OPENAI_API_KEY` (ou `ANTHROPIC_API_KEY`) nas variáveis da Vercel, o nubi usa a IA com pesquisa na web (`ia.py`) em:
- **Agente de GTIN**: quando o código de barras não está em nenhuma base, a IA procura o produto (até 15 por rodada, `NUBI_IA_GTIN_MAX`).
- **Categorias de marca**: pesquisa a origem e o tipo da marca e sugere a categoria.
- **Nomes de marcas**: "Perguntar à IA" / "Conferir todas com IA" dizem se duas grafias são a mesma marca.
- **Resumo do dia** (Vendedores → Visão geral): às 8h a IA lê a **venda isolada do dia** (o coletor baixa o export de
  1 dia de cada vendedor → `vend_vendas_dia`, com os itens vendidos), o mesmo período x mês anterior e o estoque.
  O site mostra os cards "quem mais vendeu / quem mais caiu" e "produtos em alta / em queda" (vs média dos 7 dias
  anteriores) e o texto da IA em cards por seção. Se o coletor terminar depois das 8h, o resumo sai quando a coleta termina.
- **Análise da semana**: toda segunda às 8h, com os resumos diários guardados e as vendas de cada dia x semana anterior.
- **Tarefas de rotina** (Coletor e agentes → Tarefas de rotina, tabela `rotinas`): quem faz, horário, dias, ligada e
  observação (a observação das tarefas do ChatGPT vai no prompt). A Vercel chama `r=rotinas_cron` de hora em hora e roda
  o que chegou na hora (resumo do dia, semana, marcas e o agente de GTIN). A coleta roda no Mac às 7h e só confere se
  está ligada no dia.
- **Análise mensal das marcas** (Ranking → B.I.): do dia 3 em diante, às 8h, com o relatório MARCAS do mês fechado,
  mais detalhada (categorias, entradas e saídas, oportunidades, plano do mês). Tudo fica guardado em `ia_resumos`.
