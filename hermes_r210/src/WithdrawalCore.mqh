#ifndef HERMES_WITHDRAWAL_CORE_210
#define HERMES_WITHDRAWAL_CORE_210
// Caso 7 - saque de lucro (trava de ganho).
//
// Motivacao: no Caso 4 a 5%, o pico de patrimonio chegou a ser ~136x o
// deposito inicial antes de um unico tombo devolver ~54% dele. Tecnicamente
// a maior parte do dinheiro em risco naquele momento era LUCRO do proprio
// robo, nao capital original - mas o motor de risco% nao faz essa distincao:
// ele sempre arrisca a mesma fracao do patrimonio ATUAL, para sempre, entao
// o mesmo tombo proporcional se repete a cada novo pico, com o lucro que se
// acumulou virando a nova base arriscada.
//
// Mecanismo: a cada novo recorde de SALDO REALIZADO (fechamento de trade,
// nao patrimonio flutuante - saque so faz sentido sobre lucro ja
// concretizado), uma fracao do incremento (InpWithdrawFraction, padrao 50%)
// e contabilizada como "sacada" - deixa de contar para o calculo de risco%,
// mesmo sem remover dinheiro de verdade da conta do Testador (isso seria uma
// operacao de saque real, fora do escopo testavel aqui). A margem continua
// calculada sobre o patrimonio REAL da conta - o saque so afeta o quanto e
// arriscado por trade, nunca a margem disponivel de verdade.
//
// Duas funcoes puras, independentes:
//   WDUpdate      - atualiza o estado (pico realizado, total sacado) a cada
//                   saldo observado. So age em NOVO recorde; nunca desfaz um
//                   saque ja contabilizado se o saldo cair depois.
//   WDTradingCapital - devolve o capital efetivo para sizing (patrimonio
//                   menos o total sacado, nunca negativo).
struct WDState
{
   double realizedPeak;
   double bankedWithdrawn;
};

void WDUpdate(const double balance, const double withdrawFraction, WDState &st)
{
   if (!MathIsValidNumber(balance) || !MathIsValidNumber(withdrawFraction) ||
       withdrawFraction < 0.0 || withdrawFraction > 1.0 || !MathIsValidNumber(st.realizedPeak) ||
       balance <= st.realizedPeak)
      return;
   double delta = balance - st.realizedPeak;
   st.bankedWithdrawn += delta * withdrawFraction;
   st.realizedPeak = balance;
}

double WDTradingCapital(const double equity, const double bankedWithdrawn)
{
   if (!MathIsValidNumber(equity) || !MathIsValidNumber(bankedWithdrawn))
      return 0.0;
   return MathMax(0.0, equity - bankedWithdrawn);
}
#endif
