# Pedido do Bruno (02/10 à noite): Simulador de Estratégia de Reposição

Texto do Bruno (feito com o GPT), guardado na íntegra para a implementação de 03/10 (card #151; texto completo no card).
Resumo: regra dinâmica = limite semanal de compra = X% (inicial 37%) das vendas aprovadas dos 7 dias anteriores,
dividido em segunda 40% / quarta 34% / sexta 26%; simulador testa 25%–60% de 1 em 1 no histórico (30/60/90/180 dias ou
personalizado), sem usar dado futuro, com rupturas, excesso, giro, cobertura, vendas atendidas e "venda potencial
estimada", pontuação de equilíbrio 0–100 com pesos editáveis (25/25/20/15/10/5), aprendizado × validação (60/30 em 90
dias), confiança (Alta/Média/Baixa/Dados insuficientes), gráficos, botão "Aplicar percentual recomendado" só com
confirmação e registro, estratégia adaptativa à parte, SEM nenhuma regra de caixa, e 15 testes mínimos.

O texto completo está na conversa de 02/10 (sessão de código) e foi copiado no card #151.
