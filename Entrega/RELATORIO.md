# Relatório: datalake de tracking da DadosPro

Este relatório responde às perguntas do enunciado com os números das tabelas Gold. Os números vêm da landing gerada com `python gerador/gerar_eventos.py` e processada com `python pipeline/rodar_pipeline.py`. O gerador usou a seed padrão 42 e criou 14 dias de eventos, de 01/09/2026 a 14/09/2026, com datas em UTC.

A pergunta 4 (previsão) e o job Gold de ML foram dispensados pelo professor em sala. Por isso o pipeline tem sete jobs, e não oito.

## Visão geral

| Indicador | Valor | Tabela |
| --- | --- | --- |
| Sessões (calculadas na Silver, sem `session_hint`) | 8.793 | `gold/sessoes` |
| Sessões com `page_view` na landing | 8.382 | `gold/mapa_calor_rolagem` (marco 0) |
| Pedidos (`purchase` válidos) | 573 | `gold/receita_diaria` |
| Receita bruta | R$ 338.523,10 | `gold/receita_diaria` |
| Receita reembolsada | R$ 28.608,50 | `gold/receita_diaria` |
| Receita líquida | R$ 309.914,60 | `gold/receita_diaria` |
| Ticket médio | R$ 590,79 | `gold/receita_diaria` |
| Leads (`generate_lead`) | 522 | `gold/lead_para_compra` |

## 1. Funil: em que etapa a jornada perde mais gente?

**Tabelas:** `gold/funil_compra` (linha `plano = (todos)`, `canal = (todos)`) e `gold/funil_lead`.


| Etapa              | Sessões | Conversão sobre a anterior | Conversão sobre o topo |
| ------------------ | -------- | --------------------------- | ----------------------- |
| `view_item_list`   | 5.258    | -                          | 100,0%                  |
| `select_item`      | 1.719    | **32,7%**                   | 32,7%                   |
| `add_to_cart`      | 1.291    | 75,1%                       | 24,6%                   |
| `view_cart`        | 1.255    | 97,2%                       | 23,9%                   |
| `begin_checkout`   | 912      | **72,7%**                   | 17,3%                   |
| `add_payment_info` | 684      | 75,0%                       | 13,0%                   |
| `purchase`         | 573      | 83,8%                       | 10,9%                   |

`view_item` (abrir o detalhe do plano) aparece em 57,3% das sessões com `select_item`.

**O maior vazamento é logo no topo:** de cada 100 sessões que viram a tabela de planos, só 33 clicam num plano. As outras 67 saem sem escolher nada. Dentro do checkout, a maior perda é entre o resumo do pedido (`view_cart`) e o "Continuar" do formulário (`begin_checkout`): 27% desistem ali.

**Por plano** (sessões com `select_item` → `purchase`), a conversão é praticamente igual: Pro 32,9% (803 → 264), Básico 32,8% (595 → 195) e Premium 32,1% (321 → 103). O problema não está num plano específico.

**Por canal** a diferença é grande. A tabela abaixo soma as linhas plano × canal de `funil_compra`:


| Canal                     | Viram os planos | Escolheram um plano | Compraram | Compra sobre o topo |
| ------------------------- | --------------- | ------------------- | --------- | ------------------- |
| `newsletter / email`      | 335             | 192 (57,3%)         | 74        | **22,1%**           |
| `google / cpc`            | 1.554           | 624 (40,2%)         | 221       | 14,2%               |
| `direct / (none)`         | 1.008           | 338 (33,5%)         | 112       | 11,1%               |
| `google / organic`        | 1.090           | 342 (31,4%)         | 101       | 9,3%                |
| `instagram / paid_social` | 1.271           | 223 (17,5%)         | 65        | **5,1%**            |

O Instagram traz muito tráfego, mas só 17,5% desse tráfego chega a escolher um plano.

**Funil de lead** (`gold/funil_lead`): 69% a 72% das sessões que abrem a landing rolam pelo menos até a metade da página em todos os canais. A taxa de lead fica entre 5,6% e 6,9%, menos na newsletter, com 2,6%. Faz sentido: quem vem da newsletter já é contato da empresa e não precisa deixar o e-mail de novo.

**Recomendação:** atacar a passagem tabela de planos → escolha do plano, onde a perda é maior. Algumas ideias para testar: destacar o Plano Pro como "mais escolhido", deixar a diferença entre os planos mais clara e colocar um CTA na própria tabela. No checkout, simplificar o formulário entre `view_cart` e `begin_checkout`, porque é ali que 27% desistem.

## 2. Engajamento: o vídeo é visto até o fim? O que o FAQ não responde?

**Tabelas:** `gold/retencao_video`, `gold/buscas_faq`, `gold/sessoes`, `gold/saidas_downloads` e `gold/mapa_calor_*`.

### Vídeo

Das 2.890 sessões que deram play (`video_start`):


| Marco | Sessões | % de quem deu play |
| ----- | -------- | ------------------ |
| 10%   | 2.626    | 90,9%              |
| 25%   | 2.138    | 74,0%              |
| 50%   | 1.474    | 51,0%              |
| 75%   | 1.105    | 38,2%              |
| 100%  | 877      | **30,4%**          |

**Não, o vídeo não é visto até o fim pela maioria:** só 30% de quem dá play chega ao final, e metade abandona antes da metade. O botão de play (`btn-play`) é o elemento mais clicado da landing (`mapa_calor_cliques`, intensidade 1,0, 34,5% das sessões). Ou seja, o vídeo desperta interesse, mas não segura a atenção.

Cruzando com `gold/sessoes`, assistir ao vídeo inteiro também não aumenta a compra. Sessões que viram 100% do vídeo convertem 6,5%, quase o mesmo que as que nem deram play (6,0%).

### FAQ


| Termo       | Buscas | Sem resultado |
| ----------- | ------ | ------------- |
| estagio     | 44     | **44 (100%)** |
| presencial  | 33     | **33 (100%)** |
| bolsa       | 32     | **32 (100%)** |
| power bi    | 28     | **28 (100%)** |
| linux       | 24     | **24 (100%)** |
| parcelar    | 33     | 0             |
| acesso      | 33     | 0             |
| certificado | 27     | 0             |
| reembolso   | 26     | 0             |
| apostila    | 23     | 0             |

Cinco termos nunca encontram resposta: **estágio, presencial, bolsa, Power BI e Linux**, num total de 161 das 303 buscas (53%). "Estágio" é o termo mais buscado de todos.

### Rolagem, saídas e downloads

- `mapa_calor_rolagem`: 87,8% das sessões chegam a 25% da landing, 69,5% a 50%, 50,3% a 75% e só **26,0% a 90%**. FAQ e rodapé, que ficam no fim da página, são vistos por cerca de 1 em cada 4 visitantes.
- `saidas_downloads`: a ementa em PDF teve 335 downloads. As saídas para redes sociais são poucas e equilibradas: Instagram 102, LinkedIn 92, WhatsApp 87 e YouTube 85.
- `sessoes`: a sessão média dura 149 s (mediana de 116 s), com 7 eventos.

**Recomendação:**

1. Responder no FAQ as cinco perguntas sem resposta. Se o curso tem certificado mas não tem estágio, bolsa ou aula presencial, dizer isso claramente. Se ensina Power BI e Linux, citar esses nomes nos módulos.
2. Encurtar o VSL ou trazer a oferta para antes da metade do vídeo, já que metade do público sai antes disso.
3. Subir as perguntas mais frequentes do FAQ para perto da tabela de planos, porque só 26% chegam ao fim da página.

## 3. Receita e aquisição: quanto entrou de fato e qual canal traz cliente que não desiste?

**Tabelas:** `gold/receita_diaria`, `gold/taxa_reembolso`, `gold/adesao_order_bump` e `gold/lead_para_compra`.

**Entrou de fato R$ 309.914,60.** Esse é o valor líquido: R$ 338.523,10 de receita bruta menos R$ 28.608,50 de reembolsos, em 573 pedidos. 48 pedidos foram reembolsados, uma taxa de **8,4%**.

### Por canal

Esta tabela soma `receita_diaria` e `taxa_reembolso` por canal:


| Canal                     | Pedidos | Receita bruta | Reembolsada | **Líquida**   | Taxa de reembolso |
| ------------------------- | ------- | ------------- | ----------- | -------------- | ----------------- |
| `google / cpc`            | 221     | 130.366,20    | 10.735,05   | **119.631,15** | 9,0%              |
| `direct / (none)`         | 112     | 63.417,20     | 1.273,95    | **62.143,25**  | **1,8%**          |
| `google / organic`        | 101     | 59.877,85     | 5.090,15    | **54.787,70**  | 8,9%              |
| `newsletter / email`      | 74      | 46.979,80     | 1.564,15    | **45.415,65**  | **2,7%**          |
| `instagram / paid_social` | 65      | 37.882,05     | 9.945,20    | **27.936,85**  | **23,1%**         |

- **Clientes que não desistem vêm do tráfego direto (1,8% de reembolso) e da newsletter (2,7%).** A newsletter ainda tem a maior conversão sessão → compra de todos os canais: 13,2% em `gold/sessoes`, contra 6,5% na média.
- **O Instagram é o pior canal.** Um em cada quatro pedidos é devolvido (23,1%), e 26% da receita bruta do canal volta como reembolso. No Plano Premium vindo do Instagram, a taxa chega a **40%** (6 de 15 pedidos, em `taxa_reembolso`).
- O Google pago (`cpc`) é o maior canal em volume e tem reembolso perto da média (9,0%).

### Por plano


| Plano   | Pedidos | Líquida      | Taxa de reembolso |
| ------- | ------- | ------------- | ----------------- |
| Pro     | 260     | R$ 145.795,65 | 8,1%              |
| Premium | 120     | R$ 108.812,75 | 9,2%              |
| Básico | 193     | R$ 55.306,20  | 8,3%              |

O Plano Pro responde por 47% da receita líquida.

### Order bump e leads

- **Order bump** (`adesao_order_bump`): 90 das 573 compras levaram a Mentoria em grupo, uma adesão de **15,7%**. A adesão é parecida em todos os planos: Pro 16,5%, Básico 15,0% e Premium 15,0%.
- **Lead → compra** (`lead_para_compra`): dos 522 leads, 40 compraram depois (**7,7%**), com mediana de **4,6 dias** entre o lead e a compra. Os leads do Google pago convertem mais (9,7%, mediana de 3,5 dias). Os do Google orgânico compram mais rápido (mediana de 1,9 dia). Os do Instagram convertem menos (5,3%).

**Recomendação:**

1. Rever a campanha do Instagram, cuja promessa provavelmente não bate com o curso. Uma opção é tirar o Premium dessa campanha, ou redirecionar parte da verba para o Google pago e para a newsletter.
2. Investir na base de e-mail, o canal com maior conversão e menos reembolso.
3. Como o lead leva cerca de 5 dias para comprar, uma sequência de e-mails de nutrição na primeira semana depois do download do e-book tende a aumentar a conversão de lead em compra.

## 4. Previsão

Dispensada pelo professor em sala. As tabelas `propensao_sessao`, `metricas_modelo` e `segmentos_visitantes` não foram construídas.

## Qualidade do dado

Números da rodada do pipeline sobre a landing gerada com seed 42:

| Etapa                                | Eventos   |
| ------------------------------------ | --------- |
| Linhas na landing = Bronze           | 64.372    |
| `event_id` distintos                 | 63.716    |
| **Descartados como duplicata**       | **656**   |
| **Rejeitados (um motivo por linha)** | **1.903** |
| Válidos na Silver                    | 61.813    |
| Sessões calculadas (R8)              | 8.793     |
| Itens na `silver/itens` (R10)        | 24.427    |

A conta fecha: 63.716 − 1.903 = 61.813. Cada evento rejeitado tem exatamente um motivo, então `silver/eventos_rejeitados` tem 1.903 linhas para 1.903 eventos.

### Rejeitados por motivo

| Motivo                      | Eventos | De onde vieram                                                                                  |
| --------------------------- | ------- | ----------------------------------------------------------------------------------------------- |
| timestamp ausente ou futuro | 948     | 272 com `event_ts` nulo e 676 com data em **2036**                                              |
| valor monetário inválido    | 349     | `value` negativo ou `currency = USD`, em `add_to_cart`, `view_cart`, `begin_checkout` e outros |
| marco fora do padrão        | 272     | `scroll` com `percent_scrolled` fora de {25, 50, 75, 90}                                        |
| evento fora do catálogo     | 271     | todos são `add_to_wishlist`, que não existe no contrato                                         |
| reembolso sem compra        | 32      | `refund` cujo `transaction_id` não está em nenhum `purchase` válido                             |
| transação sem id            | 31      | `purchase` sem `transaction_id`                                                                 |

### Alguma regra rejeitou dado legítimo?

Sim, em três casos.

1. **Timestamps em 2036.** Os 676 eventos "futuros" têm datas entre agosto e setembro de **2036**. Isso é exatamente 10 anos à frente, e eles estão nas partições de coleta de setembro de 2026. Provavelmente são eventos reais de navegadores com o relógio errado, e não lixo. A regra manda rejeitar e foi seguida, mas cerca de 676 eventos de comportamento real (page views, rolagens, vídeos, cliques) ficaram de fora. Duas alternativas seriam corrigir a data voltando 10 anos ou usar o dia da partição.
2. **Reembolsos de compras sem id.** O gerador injetou 31 reembolsos órfãos, mas 32 foram rejeitados como "reembolso sem compra". O reembolso a mais provavelmente é legítimo: ele deve apontar para uma das 31 compras que chegaram sem `transaction_id` e foram rejeitadas. Como essa compra não tem id, não há como ligar o reembolso a ela, e os dois ficam de fora.
3. **`add_to_wishlist`.** São 271 eventos de uma ação real do usuário, que salvou o plano na lista de desejos. Eles foram rejeitados porque esse evento não está no contrato. Não afetam nenhuma métrica pedida, mas mostram que a página emite um evento que ninguém documentou.

### Armadilhas encontradas e como foram tratadas

1. **Lotes reenviados (duplicatas).** O coletor regrava lotes, e 656 eventos chegaram mais de uma vez com o mesmo `event_id`. Na Silver, fica só a primeira ocorrência de cada `event_id`: um `row_number` ordenado por `ingestao_ts` e `arquivo_origem`. A Bronze é append-only, então rodá-la de novo duplica tudo. A mesma deduplicação também absorve esse caso: no print de execução da Silver, a Bronze tinha 128.744 linhas e a Silver saiu com os mesmos 61.813 eventos válidos.
2. **`session_hint` não é confiável.** Ele muda a cada recarga de página e daria 11.440 "sessões". A regra dos 30 minutos (R8), calculada com `lag` sobre `user_pseudo_id`, dá 8.793. Usar o hint inflaria o número de sessões em 30% e derrubaria todas as taxas de conversão.
3. **Datas no futuro e dia de coleta diferente do dia do evento.** Além dos eventos de 2036, a partição `day=` da landing é o **dia de coleta**, não o dia do evento. 683 linhas da Bronze têm os dois dias diferentes, e 13 sessões atravessam a meia-noite. Por isso as análises usam `event_timestamp` (UTC) como data do evento, e não a partição.
4. **Identidade só depois do login.** Só 903 eventos chegaram com `user_id`. Depois do identity stitching (R9), 9.472 eventos de 447 navegadores receberam o `user_id`, inclusive os eventos anteriores ao login.
5. **Números como texto em `params`.** Na Bronze, `params` é um `map<string,string>`. A Silver converte os valores com `try_cast` (por causa do modo ANSI do Spark 4). Um valor que não é número vira nulo e cai na validação, em vez de derrubar o job.
6. **Compras com dois itens.** 90 compras têm o plano **e** o order bump em `items`. Por isso a Silver explode todos os itens em `silver/itens`, em vez de pegar só `items[0]`. Pegar só o primeiro poderia devolver `BUMP-MENTORIA` no lugar do plano.
7. **O reembolso nunca acontece no dia nem na sessão da compra.** Os 48 reembolsos válidos estão em outro dia e em outra sessão, até 6,8 dias depois da compra (dentro da garantia de 7 dias). Se o reembolso fosse somado pela própria data e canal, a receita líquida de cada dia e de cada canal ficaria errada. Por isso, na Gold, ele é atribuído à compra pelo `transaction_id` e herda a data, o plano e o canal dela (`gold_receita.py`).
8. **`value` sem frete e com desconto do Pix.** 120 compras do Premium têm `shipping` (PAC ou SEDEX) num campo separado. A receita usa só `value`, sem somar o frete. O Pix já vem com 5% de desconto (231 compras com o cupom `PIX5`). Conferimos que `value` é igual à soma dos itens (vezes 0,95 no Pix) em todas as 573 compras.

## Como reproduzir

```bash
docker compose up -d floci
docker compose run --rm app python gerador/gerar_eventos.py
docker compose run --rm app python pipeline/rodar_pipeline.py
```

Depois, abra `site/index.html` e clique em Mapa de calor para ver a Gold de cliques e de rolagem desenhada sobre a página.
