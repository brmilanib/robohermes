#ifndef HERMES_EMACROSS_CORE_210
#define HERMES_EMACROSS_CORE_210
// Caso 9 - "Cruzamento EMA 5/21": pedido do proprietario, tentar melhorar a
// entrada exigindo confirmacao extra de um cruzamento RECENTE da EMA5 pelo
// lado certo da EMA21 (acima para compra, abaixo para venda), alem de tudo
// que a entrada original do Caso 1/4 ja exige. So FILTRA o lado que a
// entrada original (H1EvaluateProfile) ja escolheu - nunca decide o lado
// sozinho, nunca abre posicao sem a entrada original tambem ter disparado.
//
// Definicao de "cruzamento recente" (a unica variavel testada aqui, um
// primeiro palpite razoavel, NAO ajustada na amostra): na barra de sinal
// fechada (shift1) a EMA5 precisa estar do lado certo (>EMA21 na compra,
// <EMA21 na venda) E em ALGUMA das barras fechadas anteriores dentro da
// janela (shift2..shift(lookback+1)) a EMA5 estava do lado OPOSTO - ou seja,
// o cruzamento aconteceu de verdade dentro da janela, nao e' so um
// alinhamento antigo e estatico (o que nao seria um "cruzamento").
//
// Funcao pura, testavel fora do MT5. ema5[]/ema21[] vem em ORDEM de shift
// crescente: indice 0 = shift1 (barra de sinal), indice n-1 = shift n.

enum EMAX_GATE
{
   EMAX_READY=0,
   EMAX_DATA=400,   // dados invalidos (janela insuficiente, NaN, side invalido)
   EMAX_NONE        // EMA5 nao esta alinhada agora, ou alinhada mas sem cruzamento recente na janela
};

int EMACrossGate(const int side,const double &ema5[],const double &ema21[],const int n,int &sideOut)
{
   sideOut=0;
   if((side!=1 && side!=-1) || n<2) return EMAX_DATA;
   for(int i=0;i<n;i++) if(!MathIsValidNumber(ema5[i]) || !MathIsValidNumber(ema21[i])) return EMAX_DATA;
   bool alignedNow=(side==1) ? ema5[0]>ema21[0] : ema5[0]<ema21[0];
   if(!alignedNow) return EMAX_NONE;
   for(int i=1;i<n;i++)
     {
      bool wasOpposite=(side==1) ? ema5[i]<=ema21[i] : ema5[i]>=ema21[i];
      if(wasOpposite) { sideOut=side; return EMAX_READY; }
     }
   return EMAX_NONE;
}
#endif
