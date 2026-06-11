PreprintPDF Available

# Cryptocurrency Curated News Event Database From GDELT

- October 2022

DOI: [10.21203/rs.3.rs-2145757/v1](https://doi.org/10.21203/rs.3.rs-2145757/v1)

- License
- [CC BY 4.0](https://www.researchgate.net/deref/https%3A%2F%2Fcreativecommons.org%2Flicenses%2Fby%2F4.0%2F)

Authors:

[![Manoel Fernando Alonso Gadi](https://c5.rgstatic.net/m/448675030402/images/icons/icons/author-avatar.svg)](https://www.researchgate.net/scientific-contributions/Manoel-Fernando-Alonso-Gadi-2233703945)

[Manoel Fernando Alonso Gadi](https://www.researchgate.net/scientific-contributions/Manoel-Fernando-Alonso-Gadi-2233703945)

[Manoel Fernando Alonso Gadi](https://www.researchgate.net/scientific-contributions/Manoel-Fernando-Alonso-Gadi-2233703945)

- This person is not on ResearchGate, or hasn't claimed this research yet.


[![Miguel Ángel Sicilia](https://c5.rgstatic.net/m/448675030402/images/icons/icons/author-avatar.svg)](https://www.researchgate.net/scientific-contributions/Miguel-Angel-Sicilia-2081262138)

[Miguel Ángel Sicilia](https://www.researchgate.net/scientific-contributions/Miguel-Angel-Sicilia-2081262138)

[Miguel Ángel Sicilia](https://www.researchgate.net/scientific-contributions/Miguel-Angel-Sicilia-2081262138)

- This person is not on ResearchGate, or hasn't claimed this research yet.


Preprints and early-stage research may not have been peer reviewed yet.

[Download file PDF](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT/fulltext/63526a9e6e0d367d91affc68/Cryptocurrency-Curated-News-Event-Database-From-GDELT.pdf)

[Read file](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT#read)

[Download citation](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT/citation/download)

Copy link Link copied

* * *

[Read file](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT#read) [Download citation](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT/citation/download)
Copy link Link copied

## Abstract and Figures

Event studies in general rely on having a high-quality curated database of events. In this paper we introduce CryptoGDelt2022, a news event dataset extracted from the Global Database of Events, Language and Tone (GDELT) containing more than 243 thousands cryptocurrency related news events between the 31st of March 2021 and 30th of April 2022. The dataset is enriched with supervised machine learning scores for Relevance, Sentiment and Strength. Supervised Relevance Score measures how related to Cryptocurrency the topic is using news web scrapped from Yahoo in general and from the Cryptocurrency part of the site, after a comparison of approaches; Latent Dirichlet Allocation (LDA), BERT and Naive Bayes, Naive Bayes was chosen and the hyper-parameter tuned model reached accuracy: 97.84 % in the train set and 91.70% in the test set. Supervised Sentiment Score measures the negative, neutral or positive tone of the news, after hyper-parameter tuning, the retrained FinBERT model achieved accuracy of 92.63% in the train set and 86.11% in the test set. Supervised Strength Score measures how strong the news by using the abnormal return using Fama French 3-factor model as target output variable, after hyper-parameter tuning, the trained Naive Bayes model reached accuracy of 63.34%. The work concludes that GDELT is more reliable source of event when compared to news selected from cryptocurrency specialized websites as it presents a more balanced positive and negative number of news. All data sets and Python Jupyter Notebooks are available in the project's GitHub.

[![Methodology for generating Curated News Event Databases. Source; Gdelt [25]; Relevance Score Data Source: Yahoo Finance [26], Sentiment Score Data Source: CryptoLin [27], Strength Score Data Source: Fama French Three Factor Model [28]](https://www.researchgate.net/publication/364581962/figure/fig1/AS:11431281091234019@1666345642007/Methodology-for-generating-Curated-News-Event-Databases-Source-Gdelt-25-Relevance_Q320.jpg)](https://www.researchgate.net/figure/Methodology-for-generating-Curated-News-Event-Databases-Source-Gdelt-25-Relevance_fig1_364581962 "Figure 1: Methodology for generating Curated News Event Databases....")

[Methodology for generating Curated News Event Databases. Source; Gdelt \[25\]; Relevance Score Data Source: Yahoo Finance \[26\], Sentiment Score Data Source: CryptoLin \[27\], Strength Score Data Source: Fama French Three Factor Model \[28\]\\
\\
…](https://www.researchgate.net/figure/Methodology-for-generating-Curated-News-Event-Databases-Source-Gdelt-25-Relevance_fig1_364581962)

[![Summary frequency table of all score training.csv dataset available at the GitHub repo [29] folder Relevance](https://www.researchgate.net/publication/364581962/figure/tbl1/AS:11431281091224140@1666345642088/Summary-frequency-table-of-all-score-trainingcsv-dataset-available-at-the-GitHub-repo_Q320.jpg)](https://www.researchgate.net/figure/Summary-frequency-table-of-all-score-trainingcsv-dataset-available-at-the-GitHub-repo_tbl1_364581962 "Summary frequency table of all score training.csv dataset available at...")

[Summary frequency table of all score training.csv dataset available at the GitHub repo \[29\] folder Relevance\\
\\
…](https://www.researchgate.net/figure/Summary-frequency-table-of-all-score-trainingcsv-dataset-available-at-the-GitHub-repo_tbl1_364581962)

[![Summary frequency table of final manual labelling](https://www.researchgate.net/publication/364581962/figure/tbl2/AS:11431281091234020@1666345642180/Summary-frequency-table-of-final-manual-labelling_Q320.jpg)](https://www.researchgate.net/figure/Summary-frequency-table-of-final-manual-labelling_tbl2_364581962 "Summary frequency table of final manual labelling")

[Summary frequency table of final manual labelling\\
\\
…](https://www.researchgate.net/figure/Summary-frequency-table-of-final-manual-labelling_tbl2_364581962)

[![shows a comparison of 4 pre-trainned algorithms Vader, TextBlob,](https://www.researchgate.net/publication/364581962/figure/tbl3/AS:11431281091234021@1666345642206/shows-a-comparison-of-4-pre-trainned-algorithms-Vader-TextBlob_Q320.jpg)](https://www.researchgate.net/figure/shows-a-comparison-of-4-pre-trainned-algorithms-Vader-TextBlob_tbl3_364581962 "shows a comparison of 4 pre-trainned algorithms Vader, TextBlob,")

[shows a comparison of 4 pre-trainned algorithms Vader, TextBlob,\\
\\
…](https://www.researchgate.net/figure/shows-a-comparison-of-4-pre-trainned-algorithms-Vader-TextBlob_tbl3_364581962)

[![Sentiment class distribution](https://www.researchgate.net/publication/364581962/figure/tbl4/AS:11431281091208699@1666345642295/Sentiment-class-distribution_Q320.jpg)](https://www.researchgate.net/figure/Sentiment-class-distribution_tbl4_364581962 "Sentiment class distribution")

[Sentiment class distribution\\
\\
…](https://www.researchgate.net/figure/Sentiment-class-distribution_tbl4_364581962)

Figures - available via license: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)

Content may be subject to copyright.

![ResearchGate Logo](https://www.researchgate.net/images/icons/svgicons/researchgate-logo-white.svg)

**Discover the world's research**

- 25+ million members
- 160+ million publication pages
- 2.3+ billion citations

[Join for free](https://www.researchgate.net/signup.SignUp.html)

Available via license: [CC BY 4.0](https://www.researchgate.net/deref/https%3A%2F%2Fcreativecommons.org%2Flicenses%2Fby%2F4.0%2F)

Content may be subject to copyright.

CryptocurrencyCuratedNewsEventDatabaseFrom

GDELT

ManoelFernandoAlonsoGadi(manoel.gadi@uah.es)

University of Alcalá

MiguelÁngelSicilia

University of Alcalá

ResearchArticle

Keywords: News, Natural Language Processing, Cryptocurrency, FinBERT, Events, Labeled Dataset,

Sentiment Corpus

PostedDate: October 14th, 2022

DOI:https://doi.org/10.21203/rs.3.rs-2145757/v1

License: This work is licensed under a Creative Commons Attribution 4.0 International License. 

Read Full License

‡

Cryptocurrency Curated News Event Database From

GDELT

Mano

el

F

ernando

Alonso

Gadi

12

‡

and

Miguel

A

´

ngel

Sicilia

1

‡

1

Affiliation

Univ

ersit

y

of

Alcal

´

a

de

Hena

res

These authors contributed equally tothis work

¤

Plaza

de

San

Diego,

s/n,

28801

Alca

l

a

´

de

Henares,

Madrid,

Spain

2corresponding author’se-mail: manoel.gadi@uah.es

Madrid, Spain

Abstract

Event studies in general rely on having a high-quality curated database of

events. In this paper we introduce CryptoGDelt2022, a news event dataset

extracted from the Global Database of Events, Language and Tone (GDELT)

containing more than 243 thousands cryptocurrency related news events be-

tween the 31st of March 2021 and 30th of April 2022\. The dataset is en-

riched with supervised machine learning scores forRelevance, Sentiment and

Strength. Supervised Relevance Score measureshow related toCryptocur\-

rency the topic is using news web scrapped from Yahoo in general and from

the Cryptocurrency part of the site, aftera comparison of approaches; Latent

Dirichlet Allocation (LDA), BERT and Naive Bayes, Naive Bayes was cho\-

sen and the hyper-parameter tuned model reached accuracy: 97.84 % in the

train set and 91.70% in the test set. Supervised Sentiment Score measures the

negative, neutral orpositive tone of the news, after hyper-parameter tuning,

the retrainedFinBERT model achieved accuracy of 92.63% in the train set

and 86.11% in the test set. Supervised Strength Score measures how strong

the news byusing the abnormal returnusing Fama French 3-factor model

as target output variable, after hyper-parameter tuning, the trained Naive

Bayes model reached accuracy of 63.34%. The work concludes that GDELT

is more reliable source of event when compared to news selected from cryp-

tocurrency specialized websites asit presents a more balanced positive and

Preprint submitted toLanguage Resources andEvaluation October 10,2022

2

negative number ofnews. All data sets and Python Jupyter Notebooks are

available inthe project’sGitHub.

Keywords: News, Natural Language Processing, Cryptocurrency,

FinBERT, Events, Labeled Dataset, Sentiment Corpus

1

1\. Introduction

2

First detailed ina paper byNakamoto \[1\], Bitcoin isregarded tobe

3

the first widely adopted cryptocurrency \[2\]. Asa decentralized currency

4 and open-source online payment system Bitcoin (and other cryptocurrencies)

5 have become a fruitful area ofresearch interest across many disciplines –

6

from physics and computers science (with studies ingraph visualization)

7 \[3\]toeconomics \[2\]. Cryptocurrencies refer todigital assets that can be

8 used asa medium ofexchange between individuals orgroups. They are

9 outside ofthe traditional financial system and date back tothe firstproposal

10

ofBitcoin in2009,byananonymous individual ororganization known as

11 Nakamoto and Bitcoin.org \[1\].Cryptocurrency area form ofa decentralized

12 clearance system that provides anonymous record-keeping and transactions

13

viaa public blockchain that anyonecan see. A blockchainisa systemin

14 which transaction records aremaintained across several computers, linked

15 bya peer-to-peer network.

16

Few articles introduce corpus for finance related Natural Language Pro-

17 cessing research. For instance Daudert \[4\] introduces FinLin anannotated

18 corpus containing investor reports. Jacobs, Gilles and Hoste, Veronique \[5\]

19 presents a corpus of fine-grained company-specific events in English economic

20 news articles. Meireles etal. \[6\]focused onpresenting and proposing a con-

21 sensus mechanism. Daudert \[4\] points out that twomain challenges arises

22

when applying sentiment analysis: Relevance and Point of View. First, rele-

23 vance, can be summarised assetting up common rules for dropping irrelevant

24 news. Second, point ofview, refers to finding a common point ofview during

25

the annotation process butnone in the Cryptocurrency space.

26Although anspecific curated cryptocurrency news database does not ex\-

27 ist, several studies use small sets ofhand picked news for cryptocurrency

28 price prediction, from which wecan mention the following articles: using So\-

29

cial Media \[7\], using Tweet Volumes and Sentiment Analysis \[8\], using News

30

and Social Media Sentiment \[9\], using Sentiment Analysis\[10\], using news

31

articles \[11\], usingElon Musk’sTwitter Activity \[12\] and \[13\].

3

32Tocomplement the current resources for event studies for the specifics of

33

cryptocurrency related research. In this work, we add a third dimension to

34

this matrix we name strength, which refer to the impact an event can have,

35

and introduce CryptoGDelt2022,a novel and publicly available cryptocur-

36 rency corpus covering more than 13-months period from the 31st ofMarch

37 2021tothe 30th ofApril 2022 enhanced with with relevance, sentiment and

38 strength scores. Inaddition, weintroduce a pipeline for the selection, en\-

39 richment and assessment ofevent related corpus that can beused byothers

40 researchers when creating new corpus. The pipeline includes the training of

41 a relevance score toinclude/exclude news ifthey related tocryptocurrency,

42

re-training FinBERT for Cryptocurrency sentiment analysis and training a

43

strength score based on Fama French event study to identify events that can

44 impact the cryptocurrency world.

45The remainder ofthis paper is organized asfollows. First, Section 2

46 discusses related works onrelevance/topic modelling; sentiment/sentiment

47

corpus extraction and manual annotation and strength/event study. Section

48 3 describes our article research framework, detailing data collection, model

49 development and results for relevance, sentiment and strength score. Section

50 4 covers the generation ofthe final generated dataset with the deployment of

51 therelevance, sentiment and strength models. Section 5,weconclude with

52 some notes onfuture work.

53

2\. Related Works

54

As CryptoGDelt2022is enriched using relevance, sentiment and strength

55 score, theremainder subsections areanintroduction toeach part and pre-

56 sentation ofrelatedworks.

57

2.1. Relevance Score and Topic Modeling

58Extracting topics from a collection ofdocuments is therole ofTopic

59 Modeling which is a form ofunsupervised learning useful when annotated

60 (labeled) data is not available. Several articles use unsupervised topic mod-

61

elling Latent DirichletAllocation (LDA) for topic modelling. Lee etal. \[14\],

62

presents an automatic news categorization method using latent Dirichlet al-

63

location (LDA) and sparse representation classifier (SRC), with experimental

64 results outperforming traditional approaches. Later Guven etal. \[15\] pro-

65

posed anevolution of LDA, introducing a two stageLDA method showing

66

promising results when compared tothe conventional LDA. SeededLDA gives

4

67 theoption ofsupplying topic seed words, then the algorithm encourages top-

68 ics tobebuilt around these seed words, which forms a novel approach for

69 topic modelling called semi-supervised. Finally, Adhitama etal. \[16\] argues

70 that LDA provides a flexible way toorganize, understand, search, and sum-

71 marize electronic archives; however, it points out theinability tolabel the

72

topics that have been formed as the weakness of the LDA method.

73

We initially considered and tested the useof LDA, and even tried to give

74 thelist ofgenerated topics a manual meaning asrelated and non-related to

75

cryptocurrency,but our final approach is described at section 3.1 using a full

76 supervised approach.

77

2.2. Sentiment Score, Sentiment Analysis andcorpus annotation

78

Daudert \[4\] introduces FinLin anannotated corpus containing investor

79 reports. Jacobs, Gilles and Hoste, Veronique \[5\] presents a corpus offine-

80 grained company-specific events in English economic news articles.

81

In this article the authors web crawled news from https://finance.yahoo.com/

82 which works asa business news aggregator. Inthis work, again three anno-

83 tators, consensus decision methodology was used aseach document was fully

84 annotated bythe three annotators.

85Meireles etal. \[6\]focused on presenting and proposing a consensus mech-

86 anism. The consensus mechanism consisted oftaking the consensus of3

87

working groups (as stated inthe article, “Amodifed Delphi process (online

88 or offline survey) was utilized to create a consensus survey based onsuggested

89 recommendations from each oftheworking groups. This was performed in

90 three rounds”).The consensus mechanism was successfully tested in anan\-

91 notation ofvideo data, where annotators were formed of clinicians, engineers,

92

and data scientists and divided in work groups.

93

Existing

corpora:

In

the

specific fi

eld

of

Crypto

currency

news,

K

¨

ose

\[17\]

94 makes available a very small annotated data set with 100 hundred news

95 including cryptocurrency descriptions annotated with sector, asset type and

96

transaction anonymity labels. Forannotation, the authors mention they

97 have selected randomly one hundred news (100) from RSS feed and requested

98 three experts toannotate news’title aspositive and negative and neutral.

99

The article also points out that they were able to achieve promising results

100

by fine-tuning FinBERT with this 100news data set, butasfuture work, the

101

authors plan to increase this training data byannotating more news.

102

Forall this, our approach, a manually annotated cryptocurrency news

103 event dataset with discrete values representing negative, neutral and positive

5

104 news respectively isdescribed insection 3.2.

105

2.3. Strength Score \- Event Study

106

In the cryptocurrency space, several studies use news for cryptocurrency

107 price prediction, from which wecan mention the following articles: using

108

Social Media \[7\], using Tweet Volumes and Sentiment Analysis \[8\], using

109

News and Social Media Sentiment \[9\], using Sentiment Analysis \[10\], using

110

news articles \[11\], using Elon Musk’sTwitter Activity \[12\] and \[13\].Al-

111 though, Cryptocurrencies have become a fruitful area ofresearch interest

112 across many disciplines –from physics and computersscience (with studies

113 in graph visualization) \[3\]toeconomics \[2\].However, asfar asweknow,

114 event studies separating theeffect generated by event from thetrend/volatil-

115 ity, arestill scarce and scattered, and inmost cases centered in a subsets of

116

events and inBitcoin only. Important works in the field are:

117

•

S

ˇ

tefan

Ly

´

ocsa

et

al.

\[18\]

-

assess

how

sc

heduled

macro

economic

n

ews

118announcements affect the volatility ofbitcoin.

119•Othman etal. \[19\] \- assess the effect ofsymmetric and asymmetric

120information onvolatility structure ofbitcoin.

121•Klein etal. \[20\] - assess the effect of a subset of cryptocurrency news re\-

122lated toregulation and regulation related opinions and rumors centered

123

inbitcoin.

124•Gurrib etal. \[21\] \- assess effect major global macroeconomic news on

125several cryptocurrency price movements, including Monero.

126•Nguyen etal. \[22\]\- assess asymmetric impacts oftightening/easing

127monetary regimes onour four major cryptocurrencies including Bitcoin

128

with special attention to Chinese events impact.

129There could bevarious reasons for the small amount ofresearch onevent

130

studies inCryptocurrency, beginning withcryptocurrency remaining a very

131 volatile assets where it is still difficult toclearly isolate the proportion of

132 abnormal generated byevents from the ones reflecting its intrinsic volatility,

133

continuing with several structural differences, like being 24x7 and globally

134 traded, which requires specific studies to understand which are thekey events

135 that can trigger upa change orconservation oftrend. Nevertheless, the

136 decentralized nature ofcryptocurrencies may generate a belief that certain

6

137 events (news) are crypto-related events only (for example, crypto bans in

138

China, the creation ofa Bitcoin

ETF,

the launch ofa new blockchain, etc.)

139

and perhaps other general events (terrorism, wars, etc. .) may have an effect

140 oncrypto markets different than they doonmarkets ingeneral. Although,

141

there are contributionsinthis regard, they all rely onhaving a high quality

142 curated databaseofevents, classified bytype.

143Liu \[23\] talks about the use ofnatural language processing methods to

144

understand the valuation ofa cryptocurrency. The valuation can be under-

145

stood byusing Natural Language Processing and sentiment analysis. The

146

financial text mining process FinBERT is used to train financial corpora on

147

a large scale.Thisenables any cryptocurrency value prediction and the sig-

148 nificance. Since Bitcoins are independent of any financial corporation, this

149 kind ofprediction has a huge latency todetermining price. Wong \[24\]ap\-

150 plied twitter data topredict the sentimental analysis from the tweets. The

151 machine learning model used for this use two approaches namely generative

152

(Na¨ıveBayes model) and discriminant (LSTM). Thegenerative model uses

153

joint probability and the discriminant model uses conditional probability.

154 This uses the approach ofsentence embedding and sentiment scores from

155 Natural language processing and machine learning models.

156For all the previous, here wedepart from the hypothesis that those

157 databases should bespecific totheevents related tothe cryptocurrencies

158

and blockchaindomain (relevance), contain the point ofview (sentiment),

159 butalso measure thepotential impact ofeach news; therefore, wedescribe

160 our approach for thestrength score in section 3.3.

161

3.Research framework

162Again, Daudert \[4\] points out that twomain challenges arises when ap\-

163

plying sentiment analysis: Relevance and Point ofView. Relevance, can be

164 summarised assetting upcommon rules for dropping irrelevant news. Inthis

165 work weadd a third dimension tothis matrix wename strength ascan be

166 seen in figure 3.

167Figure 3 shows the whole process starting from downloading thenews

168

from Gdelt (using gdeltdoc,  https://github.com/alex9smith/gdelt-doc-api,

169 Python package version: 1.4.0), developing relevance, sentiment and strength

170 scores in each specific dataset respectively tofinally deploy all models prob-

171

ability and class into the  final  CryptoGDelt2022. Westart the process

172 downloading more than one year ofnews containing any ofthekeywords:

7

Figure 1:Methodology for generatingCurated  News Event Databases. Source; Gdelt

\[25\]; Relevance Score Data Source: Yahoo Finance \[26\], Sentiment Score Data Source:

CryptoLin \[27\], Strength Score Data Source: Fama French Three Factor Model \[28\]

173

cryptocurrency,cryptocurrencies,CBDC,Bitcoin, Ethereum, Litecoin, Bitco-

174

inCash, BitcoinSV, Polkadot, Chainlink, BinanceCoin, VeChain, Cosmos,

175

Polkadot, NEO, Tezos, Tether, USDCoin, Monero, Dash, Zcash, Ripple, Car-

176

dano, Stellar, CounosX, crypto, btc,eth, USDT, dai, NFT, Satoshi, XRP,

177 Stablecoin. For anyone interested onreproducing theinitial download, a

178 Jupyter notebook isavailable at\[29\]Github repository under the name:

179

CryptoGDelt2022GDELT initial download.ipynb, but we alert not to reduce

180 thesleep time under 5seconds toavoid being blocked out byGdelt.

181

Below is a list of 5 steps toreproduce the creation ofCryptoGDelt2022.csv

182 using the codes available atthegithub repository \[29\]:

183

1\.

Run CryptoGDelt2022

GDELT

initial download.ipynb

: this code

184downloads the whole period of news from Gdelt - it maytake more than

185a week todoso, recommended toskip this part for reproduction.

8

186•development dataset (Dev): None

187•deployment dataset input (Dep.I): None

188•deployment dataset output (Dep.O): OneYearNewsDataset.csv

189

2\.

Run Relevance/ToReproduceRelevance.ipynb

: this code train

190thesupervised relevance score using all score training.csv dataset and

191deploy it tothe pipe ofnews downloaded from Gdelt in anaddictive

192manner.

193•Dev: Relevance/all score training.csv

194•Dep.I: OneYearNewsDataset.csv

195•Dep.O: OneYearNewsDataset AfterRelevance.csv

196

3\.

Run Sentiment/ToReproduceSentiment.ipynb

: this coderetrain

197

Finbert sentiment score using CryptoLin

IE

v2.csv dataset and deploy

198it tothe pipe ofnews downloaded from Gdelt in anaddictive manner

199\- it maytake more than 12hours torun this step.

200

•

Dev: Sentiment/CryptoLinIEv2.csv

201•Dep.I: OneYearNewsDataset AfterRelevance.csv

202•Dep.O: OneYearNewsDataset AfterSentiment.csv

203

4\.

Run Sentiment/ToReproduceStrength.ipynb

: this code train the

204

Strength score based on Fama French using Strength/FF3 daily.csv and

205

Strength/news short.xlsx datasets anddeployittothe pipe ofnews

206

downloaded from Gdelt in an addictive manner.

207

•

Dev: Strength/FF3 daily.csv and Strength/news short.xlsx

208•Dep.I: OneYearNewsDataset AfterSentiment.csv

209•Dep.O: OneYearNewsDataset AfterStrength.csv

210

OneYearNewsDataset AfterStrength.csv is the final dataset and it sim-

211

ilar toCryptoGDelt2022.csv, this last onecontains some extra date

212fields used for sorting the news bydate and time.

213

5\.

Optionally run CryptoGDelt2022 EDA.ipynb

: this code outputs

214

an EDA ofthe generated dataset.

215The remaining ofthis section describes the methodology and development

216 ofrelevance, sentiment and strength scores.

9

217

3.1. Relevance Score

218Although several articles uses unsupervised topic modelling Latent Dirich-

219

let Allocation (LDA) forclassificationofthe topic discussed ina news tittle

220 (Lee etal. \[14\], Adhitama etal. \[16\], Guven etal. \[15\]) and initially consid-

221 ered doing the same, but a supervised Naive Bayes approach was the chosen

222 option. For the supervised techniques a labeled dataset was required, in

223 order toprepare such dataset news was web scrapped from Finance \[26\].

224 Table 1 shows a frequency table ofofthe all score training.csv dataset avail-

225 able attheGitHub repository \[29\] folder Relevance (also, a Jupyter Notebook

226 named ToReproduceRelevance.ipynb is available for reproducibility purposes

227

in the same folder). 1187 generic news (no related to cryptocurrency) were

228 extracted from Yahoo! (https://news.yahoo.com/) and labeled as1;546 re\-

229

lated tocryptocurrency newswere extractedfrom Yahoo!  FinanceCrypto

230 (https://finance.yahoo.com/topic/crypto) and labeled 1,a total of1733 news

231 web scrapped during a period oftwoweeks in June/2022.

Table 1: Summary frequency table of all score training.csv dataset available at the GitHub

repo \[29\] folder Relevance

relevance

count

% oftotal

0 (no related tocryptocurrency)

1187

68.5%

1 (yes related to cryptocurrency)

546

31.5%

total

1733

100.00%

232

Thelabeled dataset was used for training theNLP classification model

233

that aims to distinguish between crypto related or non-crypto related news.

234

A BERT

model was trained and compared with a simple Naive Bayesap-

235

proach. For both models, the results were similar in terms ofaccuracy and

236 thesimple NaıveBayes approach was defined asthe optimal one for pro-

237 duction purposes, asthere was noconsiderable benefit in performance that

238

justified the increase inthe model complexity. In both scenarios, the news

239

titles were preprocessed with different NLP techniquesinorder toverify

240

whether the classificationresult could improve. Being a text classification

241 problem, thetext was normalized tolower case, punctuation was removed

242

aswell asstop-words, and lemmatization was applied aswell inorder to

243 standardize text asmuch aspossible. The implementation ofthe previously

244 mentioned techniques increased theclassification accuracy in3.3pp.

245

Table 2 showsthe data was split into 1299news fortraining and 434

246 news for test data achieving the following accuracy, precision, recall, f1-score

10

247 and AUC: 97.84 %,98.47%, 94.62%, 96.50% and 96.97% inthetrain set and

248 91.70%, 98.09%, 75.18%, 85.12% and 87.25% inthe test set.

Table 2: SupervisedNaive Bayes Relevance Score built onall score training.csv dataset

available atthe GitHub repo \[29\] folder Relevance

split

count

accuracy

precision

recall

f1-score

AUC

train

1299

97.84 %

98.47%

94.62%

96.50%

96.97%

test

434

91.70%

98.09%

75.18%

85.12%

87.25%

249

3.2. Sentiment Score

250Supervised Sentiment Score measures thenegative, neutral orpositive

251 tone ofthe news \- For sentiment score, a set of pre-trainned algorithms were

252

compared, with the final retraining ofFinBERT algorithm using few-shot

253

learning strategy (FSL) with the CryptoLinIE dataset being the best option,

254

CryptoLin

IE

v2.csv dataset is available at the GitHub repository \[29\] folder

255

Sentiment (also, a Jupyter Notebook named ToReproduceSentiment.ipynb is

256

available for reproducibility purposes in the same folder)

257

Main articles onFSLare: Yang et al. \[30\], Zhanget al. \[31\], Finnet al.

258

\[32\], Snell et al. \[33\] and Brown et al. \[34\]) describe itasan strategy to learn

259 a task byusing only a few supervised (labeled) examples ofthe total sample.

260

The data create specially for this FSL task was CryptoLinIE, a manually

261 annotated cryptocurrency news event data set with discrete values represent-

262

ing negative, neutral and positive news respectively. CryptoLinIE wasex-

263 tracted from https://coinmarketcal.com/en/news containing 2683 news from

264

July 2018 toJanuary 2022with 1236 positive news, 1134neutral news and

265

313 negative news. 84

IE

Business School master in Big Data students partic-

266 ipated inthe annotation process, each news title was randomly assigned and

267 blindly annotated by 3 human annotators followed by a consensus mechanism

268 using simple voting. Incase one oftheannotators was intotal disagreement

269

with other two (1negative vs2 positive or1 positive vs2 negative), we

270 considered this minority report and defaulted the labeling toneutral. Both

271

the CryptoLinIE data set and the Jupyter Notebook with the analysis, for

272

reproducibilitypurposes, are available atthe project’sGithub repository:

273

CryptoLin

IE

v2.csv dataset is available at the GitHub repository \[29\] folder

274

Sentiment (also, a Jupyter Notebook named ToReproduceSentiment.ipynb is

275

available for reproducibility purposes in the same folder).

11

{

Table 3:Table containing the first news extracted from CoinMarketCal  website (\[35\]),

final manual labelling refers to the consensus of sentiments 1, 1 and 1 from randomly

assigned annotators 22,71and59respectively

key value

id

0

date 1/25/2022

news Ripple announces stock buyback, nabs$15billion valuation

final manual labelling1

text span annotator1 id: 22;annotator1 label: 1;

annotator2 id:71;annotator2 label2: 1;

annotator3 id: 59; annotator3 label: 1}

276Table 3 shows a pivoted version ofthefirst row ofthe CryptoLinIE data

277 set selecting only the the first five columns ofthe data set. Here one can

278 observe the consensus 1 (positive) being achieved from assessed sentiments

279

1,0 and 1 from randomly assigned annotators id=6, id=23 and id=17 re-

280 spectively.

281Table 4 presents theconsensus mechanism used. Column decision indi-

282 cates thefinal manual labelling assigned depending onannotation given by

283 annotator 1,2 and 3,Column reasoning gives anexplanation ofthe decision.

284 Row one one of the table shows that if annotator 1,annotator 2 and annota-

285 tor 3 marka news asnegative the final label (or decision) is negative and the

286

reasoning forthat decision iscomplete majority. TheCryptoLinIE dataset

287 presents 380news with that combinationoflabelling. Note minority report

288 todefault the labelling toneutral incase ofone objection is used. Count

289 represents the number ofoccurrences inthedata set.

290Table 5 shows a frequency table of final manual labelling column generate

291

out of CrypLinIE.csv.Having 385 news manually labelled asnegative a

292 14.35% ofthe total, 942news manually labelledasneutral a 35.11% ofthe

293 total and 1356 news manually labelled aspositive a 14.35% ofthe total.

294

Table 6  shows Fleiss’s Kappa, Krippendorff’s  Alpha  and Gwet’s AC1

295

inter-rater reliability coefficients demonstrating CryptlinIE’s acceptable qual-

296

ity of inter-annotator agreement.

297Next, weassessed the four pre-trained Sentiment Analysis models Vader\[41\],

298

Textblob\[42\], Flair\[43\] and FinBERT \[23\] using CryptoLinIE dataset.

299•Vader Sentiment Analysis (Hutto and Gilbert \[41\]),

300

•

TextBlob Sentiment Analysis (Loria \[42\]),

12

Table 4: Consensus table. Column decision indicates the final manual labelling assigned

depending on annotation given by annotator 1, 2 and 3, Column reasoning gives an ex-

planation ofthe decision. Note minority report to default the labelling toneutral in case

of one objection is used. Count represents the number ofoccurrences in the data set.

annotator 1

annotator 2

annotator 3

decision

reasoning

count

-1

-1

-1

-1

complete majority

380

-1

-1

0

-1

majority with noobjection

3

-1

-1

1

0

minority report, majority with oneobjection

2

-1

0

0

0

majority

6

-1

1

-1

0

minority report, majority with oneobjection

1

-1

1

0

0

total disagreement

2

-1

1

1

0

minority report, majority with oneobjection

2

0

-1

-1

-1

majority with noobjection

2

0

-1

0

0

majority

3

0

-1

1

0

total disagreement

3

0

0

-1

0

majority

6

0

0

0

0

complete majority

864

0

0

1

0

majority

13

0

1

-1

0

total disagreement

1

0

1

0

0

majority

13

0

1

1

1

majority with noobjection

17

1

-1

-1

0

minority report, majority with oneobjection

2

1

-1

0

0

total disagreement

3

1

-1

1

0

minority report, majority with one objection

2

1

0

-1

0

total disagreement

1

1

0

0

0

majority

15

1

0

1

1

majority with noobjection

21

1

1

-1

0

minority report, majority with one objection

3

1

1

0

1

majority with noobjection

13

1

1

1

1

complete majority

1305

2683

Table 5:Summary frequency table of final manual labelling

301

•

Flair NLP library (Akbik \[43\]),

302

•

FinBERT Financial Sentiment Analysis with BERT (Liu \[23\]), for Fin-

303

BERT

we include the 3 predictions \- finbert positive, finbert negative

304and finbert neutral scores.

305Table 7 shows a comparison of4 pre-trainned algorithms Vader, TextBlob,

final manual labelling

count

% oftotal

-1 (negative sentiment)

385

14.35%

0 (neutral sentiment)

942

35.11%

1 (positive sentiment)

1356

50.54%

total

2683

100.00%

13

Table 6: Fleiss’s Kappa, Krippendorff’s Alpha and Gwet’s AC1 inter-rater reliability co-

efficients annotators1 and2 (Coeff (1-2)), 1 and3 (Coeff (1-3)) and2 and3(Coeff (2-3))

andits benchmark interpretation according toLandis andKoch \[36\], Fleiss \[37\], Altman

\[38\] and Cicchetti \[39\] benchmarks on the aligned span annotations using the Multi Class

Confusion Matrix Library for Python provided by Haghighi etal. \[40\]

Metric

Coeff (1-2)

Coeff (1-3)

Coeff (2-3)

Fleiss’κ

0.942

0.942

0.944

Kappa’sStdErr

0.006

0.006

0.006

Kappa’s95% C.I.

(0.958, 0.972)

(0.958, 0.972)

(0.96, 0.973)

Krippendorff’sα

0.942

0.942

0.944

Gwet’s AC1

0.9499

0.9499

0.952

Landis andKoch \[36\] benchmark

Almost Perfect

Almost Perfect

Almost Perfect

Fleiss \[37\] benchmark

Excellent

Excellent

Excellent

Altman \[38\] benchmark

Very Good

Very Good

Very Good

Cicchetti \[39\] benchmark

Excellent

Excellent

Excellent

Table 7: Comparison of four pre-trainned algorithms in CryptoLinIE. TextBlob and Flair

show poor performance. Vader and FinBERT show reasonable performance demonstrat-

ing data was not annotated randomly, in other words, the labelling is useful. FinBERT

(negative) presents best performance indicating advantage of its expertise in the financial

field

Sentiment Algorithm best negative threshold best positive threshold accuracy

Vader 0.0 0.0258 44.2%

TextBlob 0.00568 (no neutral found) 0.00568 26.91%

Flair 0.94471 (no neutral found)0.94471 23.56 %

finbert positive 0.05466 0.08026 54.98%

finbert negative -0.03882 -0.01521 58.93%

finbert neutra 0.62899 0.68332 38.54%

306

Flair and FinBert using each of its predictions. we applied roc curve method

307 (from sklearn.metrics) to find out the two best threshold for each pre-trainned

308 algorithm in order toturn thesentiment score into class -1 (negative), 0

309

(neutral) and1 (positive).  For doing that, wecreated two target variables

310 y else ornegative and y positive orelse. Next, weapplied roc curve method

311 (from sklearn.metrics) which returns the best threshold for each algorithm

312

and the target variables y else ornegative and y positive orelse resulting

313

into the best negative threshold and best positive threshold respectively. In

314 thecase ofTextBlob and Flair bothnegative and positivethresholds resulted

315 in equal values meaning nonews were classified asneutral, emphasising the

316 poor performance ofno-financial related sentiment algorithms in this data.

317However, the weak performance of all pre-trained models drove us for the

14

318

retraining ofFinBERT the CryptoLinIE dataset. Table 8 shows the split

319 ofthedata into 2147 news for training and 536 news for testing the model

320 and the results after the hyper-parameter tuning process tofind the best pa\-

321

rameters improved the accuracy of the retrained

FinBERT

model. The final

322 model achieved anoverall 92.64% ofaccuracy in the test dataset, with the

323 following precision, recall and f1-score byclass: Positive class 98.11%,80.00%

324 and 88.14%, Negative class 95.00%, 95.00% and 95.00%, and Neutral class

325 62.86%, 95.65% and 75.86%.

Table 8: Results of retrained fine tuned FinBERT model CryptoLinIE on test split (\[29\]

folder Sentiment) - overall accuracy 92.64% and 86.11% in train and test split respectively

with all sentiments combined

type ofsentiment

precision

recall

f1-score

negative

98.11%

80.00%

88.14%%

neutral

95.00%

95.00%

95.00%

positive

62.86%

95.65%

75.86%

326

Setofbest FinBERT hyper-parameters available atannex.

327

3.3. Strength Score

328News strength refers tothe power ofa single news, ora set ofnews, in

329 a give day, that triggers positive ornegative abnormal returns ofanasset.

330

Cryptocurrency market isvery volatile, sothe strength ofnews must be

331 carefully studied tounderstand which are the key events that can trigger

332 upa change orpotentiate a trend. Hence, it is important toanalyse the

333

diverse set ofevents and classify them, for eventually obtaining a potential

334 significance level for determining their strength. For example, the central

335 banks report from the Fed about upcoming digital currency \[44\] alone has

336

caused the fall ofBitcoin prices in the days following its publication.

337\[45\]shows the application of the French three factor topredict the return

338 oftheBitcoins. The factors used byFamais used todetermine the volatility,

339 risk, value toreturn and excess returns ofBitcoins. The use ofNatural

340 processing language and financial data models haveenabled predictions and

341 rapid increase ofgrowth ofBitcoins.

342

Fama French Three Factor Model forobtaining the excess of return within

343 anasset can beconsidered asanextension ofthe traditional Capital Asset

344

Pricing Model (CAPM) but with the addition oftwo extra components \[46\].

15

345 This model will beapplied within a selected number ofnews with the pur\-

346 pose ofunderstanding the impact ofthose events within thevaluation ofthe

347 selected cryptocurrency.

348Assupport data set was obtained from French \[47\] website, which pro-

349

vided the Market Factor, Size Factor, Value Factor, and Risk Free Rate for

350 theFamaand French Three Factor Model\[46\]. This can beseen in Table 2,

351 where data is ordered according todates.

Table 9:Market Factor,Size Factor, Value Factor, andRisk Free Rate for the Fama and

French Three Factor Model from website (\[47\] )

Date Mkt-RF

SMB

HML RF

20180730

-0.7 -0.22 1.57 0.008

20180731

0.51 0.85 -1.11 0.008

20180801

-0.13 0.06 -0.19 0.007

20180802

0.67 0.32 -0.67 0.007

20180803

0.31 -1.07 0.51 0.007

20180806

0.46 0.25 -0.33 0.007

20180807

0.29 0.03 -0.16 0.007

20180808

-0.04 -0.12 0.26 0.007

20180809

-0.05 0.37 -0.36 0.007

20180810

-0.6 0.39 -0.21 0.007

20180813

-0.46 -0.14 -0.3 0.007

20180814

0.69 0.3 0.21 0.007

20180815

-0.91 -0.54 -0.12 0.007

20180816

0.86 -0.07 0.26 0.007

20180817

0.3 0.09 0.02 0.007

20180820

0.25 0.12 0.14 0.007

20180821

0.33 0.9 0.12 0.007

20180822

0.05 0.37 -0.35 0.007

20180823

-0.19 -0.06 -0.33 0.007

20180824

0.62 -0.02 -0.57 0.007

20180827

0.74 -0.68 -0.17 0.007

20180828

-0.01 -0.12 -0.28 0.007

20180829

0.56 -0.04 -0.57 0.007

20180830

-0.41 0.28 -0.42 0.007

20180831

0.08 0.5 -0.39 0.007

20180904

-0.11 -0.38 0 0.008

20180905

-0.41 -0.17 0.66 0.008

20180906

-0.44 -0.35 -0.24 0.008

20180907

-0.18 0.1 -0.21 0.008

20180910

0.23 0.12 -0.37 0.008

: : : : :

: : :: :

20211227

1.22 -0.09 0.28 0

352

Returns Calculation:

353

Forthe present analysis Fama French Three Factor model was applied,

354 which can bedefined asthe estimation ofexcess ofresults within investment

355 assets \[46\]. For that purpose itconsists onusing two more factors apart from

356

the original Market Risk thatis already used within the typical Capital Asset

16

−

357

Pricing Model (CAPM)\[46\]. Theequation ofthis model can bedefined as

358 follows:

R

a

= R

f

\+ β

1

(Mkt

−

R

f

) \+ β

2

(SMB) \+ β

3

(HML) \+ α

359

R

a

=

Expected return on asset

360

R

f

=

Risk-free rate

361

β

123

= Factor coefficient

362

Mkt

R

f

= Market risk premium

363

SMB(Small Minus Big)

=

Excess returns of small cap over large cap

364

HML(High Minus Low) = Excess returns of value stock over growth stocks

365

α= Intercept

366Asobserved inthe previous equation, this model consist ontheuse of

367 three specific factors: the Market Factor, the Size Factor and the Value Fac\-

368 tor. The first one consist onthe excess ofreturn regarding the market value,

369

a typical factor applied within CAPM method. Thesecond one, refers to

370

the excess return between companies with small market capitalization with

371

the ones that belong tolarge market capitalization \[46\]. This factorisused

372 with the purpose ofmeasuring theproportionality ofanimpact consider-

373 ing thewhole scope ofanindustry. The third and last one correspond to

374 theexcess return that is generated between value stocks and growth ones

375 \[46\].Hence, FamaFrench develops a framework that allows tohave a better

376 market benchmark which intheend helps toassess in a wider extent the

377 performance ofaninvestment.

378For developing the complete analysis ofthe effect ofthe selected events,

379 a time frame of7 days was added sothat daily valuations were compared.

380 Inthat sense, the 2 previous days totherelease ofthe news were taken

381 into consideration and 4 days after it, considering the current date asday 0.

382 The results for the 7 days were inserted into thetable and upon that it was

383 assessed if ithad a positive ornegative change.

384Data for the Strength Score was acquired from French \[12\] website con-

385

taining 25251 daysfrom 1stofJune 1926 to31th ofMay2022\. A model

386 was prepared considering thereturns ofBitcoin (since it is the cryptocur-

387

rency that better reflect the overall market sentiment regarding crypto) by

388 extracting theprice evolution and calculating thepercentage change per day

389

from Yahoo! throughout the study period. An event study analysis was con-

390 ducted, considering theeffects ofthat percentage change onaperiod range

17

391

of 2 days before and 4 days after the particular date of the returns. A sliding

392 window approach with 700 samples \- days \- was used toestimate the next-

393

day return and compare itto the real one. A ratio of expected to real return

394 in absolute terms higher than 180 (i.e. 6 months), yielded onanabnormal

395 label for that specific date, whereas a lower ratio implied a normal label. The

396 data was then merged with a specific set ofnews ofthose particular dates in

397

order tocreate anNLP classification model toidentify, using the news,ifa

398 given day would beabnormal ornot.

399A simple Na¨ıveBayes classifier with default parameters was selected as

400

NLP model and trained from 12th March 2022 to 7th April 2022, with 10days

401 with abnormal positive returns, 2 days with abnormal negative returns days

402 and 15days with normal returns. Classes were combinedinto 12abnormal

403 returns days and 15normal returns.

404The dataset of news contained 20263 observations, between the previously

405 defined trained period, that were split into 70%for training and 30%for

406

testing. The accuracy of the NLP classification model was low, only reaching

407

a 64.35% inthe test dataset.  Further analysis asmodel tuning,other NLP

408 model’sevaluation or a different labeling approach, for defining ifa given day

409

will be abnormal or not, should be consider in order to improve the accuracy

410 ofthe Strength Score.

411

4\. Results

412

The final dataset called CryptoGDelt2022 isavailable at\[29\] with its de-

413

tailed EDA Jupyter Notebook for reproducibility, the dataset isan extraction

414 ofnews event from Gdelt and application ofthe three models relevance, sen-

415 timent and strength scores, below wepresent themostrelevant stats ofthe

416 dataset:

417•243422 rows and 19columns

418

•

First date

=

2021-03-31 00:00:00 / Last date

=

2022-04-30 00:15:00

419Table 10shows the first row ofthat dataset, below is a description of each

420 field:

421•id: row number identifier

422•url: url oforiginal news

18

Table 10: CryptoGDelt2022 pivoted first row with relevance equals to1 (\[29\] )

Field Value

id

4

url https://www.kcra.com/article/chipotle-is-giving-away-100k-in-bitcoin/35984129

url mobile https://www.kcra.com/amp/article/chipotle-is-giving-away-100k-in-bitcoin/35984129

title chipotle giving away 100k bitcoin

seendate 20210331T000000Z

socialimage https://kubrick....

domain kcra.com

language English

sourcecountry United States

lemmetized titles chipotle giving away 100kbitcoin

relevance probability

0.539298

relevance class

1.0

sentiment negative probability

0.003012

sentiment neutral probability

0.025706

sentiment positive probability

0.971283

sentiment class

1

strength score

1

date format

2021-03-31

datetime 202103-3100:00:00

423•url mobile: url for mobile devices

424•title: news title

425•seendate: date the news were first seen

426•socialimage: image url

427•domain: news original source domain

428•language: language ofthe article

429•sourcecountry: country ofthenews

430•lemmetized titles: news title after grouping together the inflected forms

431ofa word and elimating stop words

432•relevance class: class prediction ofthe Relevance Score (0\- noncrypto

433

related / 1 \- yes crypto related)

434•relevance probability: Relevance Score estimated probability ofnews

435being crypto related

436•relevance class: 1 if relevance probability greater than 50%, 0 otherwise

19

437•sentiment negative probability: Sentiment Score (Re-trained Fine Tuned

438

FinBERT) estimated probability ofnews being negative

439

•

sentiment neutral probabilit: Sentiment Score (Re-trained Fine Tuned

440

FinBERT) estimated probability ofnews being neutral

441•sentiment positive probability: Sentiment Score (Re-trained Fine Tuned

442

FinBERT) estimated probability of news being positive

443

•

sentiment class: Sentiment Score (Re-trained Fine Tuned FinBERT)

444

class: -1:negative / 0:neutral / 1:positive

445•strength score: Strength Score (from FamaFrench) estimated proba-

446bility ofnews generating anabnormal return for Bitcoin

447•date format: date extracted from seendate

448•datetime: date and time extracted from seendate

Table 11: CryptoGDelt2022 scores’summary statistics

score

count

mean

std

min

25%

50%

75%

max

relevance probability

243422.0

0.365207

0.176954

0.016472

0.231597

0.324303

0.473571

0.983138

sentiment negative probability

243422.0

0.158769

0.303045

0.001313

0.008902

0.014592

0.067717

0.987690

sentiment neutral probability

243422.0

0.483232

0.363384

0.005555

0.089831

0.489286

0.867897

0.971657

sentiment positive probability

243422.0

0.357999

0.363488

0.002367

0.043732

0.165156

0.744326

0.990510

strength score

243422.0

0.669163

0.470515

0.000000

0.000000

1.000000

1.000000

1.000000

449

Table 11 and figure 2 show CryptoGDelt2022 the scores’ summary statis-

450 tics and histogram showing anacceptable level ofspread for all sentiment,

451 strength and sntiment scores, looking into the graph the only measure appar-

452

ently normal isstrength probability and thisisconfirmed byShapiro Nor-

453

mality Test:

454•relevance probability not normal according toShapiro test: ShapiroRe-

455

sult(statistic=0.9496811032295227, pvalue=0.0)

456•sentiment negative probability not normal according toShapiro test:

457

ShapiroResult(statistic=0.5469046831130981, pvalue=0.0)

458•sentiment neutral probability not normal according toShapiro test:

459

ShapiroResult(statistic=0.8516964912414551, pvalue=0.0)

20

Figure 2:CryptoGDelt2022 histogram showing an acceptable level of spread for all scores

460•sentiment positive probability not normal according toShapiro test:

461

ShapiroResult(statistic=0.8047546148300171, pvalue=0.0)

462

•

strength probability

isnormal

according toShapiro test: ShapiroRe-

463sult(statistic=0.997541069984436, pvalue=7.987401246651457e-44)

Table 12: Relevance classdistribution

train dataset train dataset CryptoGDelt2022 CryptoGDelt2022

class

count

percentage

count

percentage

0 (non-relevant)

1187

68.49%

190115

78.10%

1 (relevant)

546

31.51%

53307

21.90%

Table 13: Sentiment class distribution

train dataset train dataset CryptoGDelt2022 CryptoGDelt2022

class

count

percentage

count

percentage

-1 (negative)

396

14.76%

37094

15.24%

0 (neutral)

921

34.33%

122966

50.51%

1 (positive)

1366

50.91%

83362

34.25%

21

Table 14: Strength classdistribution

class

train dataset

count

train dataset

percentage

CryptoGDelt2022

count

CryptoGDelt2022

percentage

0 (weak)

1187

68.49%

79607

32.70%

1 (strong)

9604

47.40%

163815

67.30%

464

5\. Conclusions

465Although few articles introduce corpusfor finance related Natural Lan-

466 guage Processing research (\[4\], \[5\], \[6\]), anspecific curated cryptocurrency

467 news database does not exist. Nevertheless, the demand for such dataset ex\-

468 ists asseveral studies use small sets ofhand picked news for cryptocurrency

469 price prediction (\[7\], \[8\], \[9\], \[10\], \[11\], \[12\] and \[13\]).

470Tocomplement the current resources for event studies for the specifics of

471 cryptocurrency related research. This work has introduced CryptoGDelt2022,

472

a novel and publicly available cryptocurrency corpus covering more than

473 13-months period from the 31st ofMarch 2021 tothe 30th ofApril 2022

474 enhanced with with relevance, sentiment and strength scores.

475Table 12,13and 14show the distribution ofrelevance, sentiment and

476

strength classes respectively. From which we can conclude:

477•Relevance model shows an increase of non-relevant news between train-

478ing (68.49%) and deployment (78.10%) which wecan conclude that

479

indicates that the fine-tuned model isaccomplishing its objective of

480

indicating relevant news.

481•Sentiment model shows an important decrease of positive news between

482

training (50.91%) and deployment (34.25%) which indicates, that com-

483

ing directly from Gdelt, CryptoGDelt2022 isless positive bias than

484news selected from cryptocurrency specialized websites like \[27\], from

485

which wecan conclude that Gdelt is the right source for cryptocurrency

486news.

487•Strength model shows anintriguing shift ofleading category between

488between training and deployment, which is not very clear why and

489

further investigation ofthe Fama French 3 vs5 vsother alternatives

490is necessary toeither confirm the shift ortocorrectly choose the most

491suitable model for measuring news strength.

22

492

.

493

Forall these wecan conclude that CryptoGDelt2022 isofgood quality

494

and can be considered an advance to society asitopens the opportunity for

495 several other research lines.

496

5.1. Future researches and implication for society

497

Possible future research lines using CryptoGDelt2022:

498•assessment ofcryptocurrencies prices and level ofadoption asinvest-

499ment asset,

500•assessment of the adoption of cryptocurrency as payment option option

501byregion over time

502

•

analysis fraud detection modus operandi oncryptocurrencymarkets

503for central banks, regulators and investors,

504•furthermore, the 3-scores pipeline proposed in this paper can betested

505in other new event studies,

506•finally, further analysis oftheFamaFrench model with potential com-

507parison of3 and 5 factors models and its hyper parameters against

508its level ofdays with abnormal returns is recommended topower the

509strength model further.

510

5.2. Data availability

511

For reproducibility purposes, all files related tothe project areavailable at

512

the project’s Github \[29\] - https://github.com/manoelgadi/CryptoGDelt2022.

513

Themain file istheCryptoGDelt2022.csv dataset, a GDELT news event

514 dataset extraction containing more than 243 thousands cryptocurrency re\-

515 lated news events from 31st ofMarch 2021 to the 30th of April 2022 enriched

516 with relevance, sentiment and strength scores.

517

CryptoGDelt2022EDA.ipynb notebook holds a simple EDA ofthe Cryp-

518

toGDelt2022.csv.

519

In each folder Relevance, Sentiment and Strength a Python Jupyter note-

520

book called ToReproduce\[Relevance/Sentiment/Strength\].ipynbis available

521

for reproducibility purposes of each model creation and its application into

522

CryptoGDelt2022.csv.

23

523•Relevance folder holds the relevance score model building (target: 1

524news from https://finance.yahoo.com/topic/crypto and 0 news from

525

https://news.yahoo.com, method: pipeline ofTfidfVectorizer and Multi-

526

nomialNB),

527•Sentiment folder holds thesentiment score model building (target:

528

manual labelled byIEBusiness School students / method: retraining

529

FinBERT) and

530•Strength folder holds thestrength score model building (target: Fama

531

French Threefactor / method: pipeline ofTfidfVectorizer and Multi-

532

nomialNB).

533 5.3. Acknowledgement

534

I would like to express my gratitude toall mystudents from spring 2022 of

535

the course Risk and Fraud Analytics in the Master ofBig Data and Business

536

Analytics atIEUniversity in Spain for the valuable support tothis research.

537

538

5.4. Author’scontribution, Conflict ofInterestandFunding Information

539Weconfirm that both authors have collaborated equally tothe work, we

540 have no conflicts ofinterest todisclose and wehave not received any funding

541 for thecurrent work.

542

References

543

\[1\] S. Nakamoto, Bitcoin.org, Bitcoin: a peer-to-peer electronic cash system

544

(2008) 9\. URL: https://bitcoin.org/bitcoin.pdf.

545

\[2\]E. Demir, G. Gozgor, C.K.M. Lau, S.A. Vigne, Does economic policy

546

uncertainty predict the bitcoin returns? anempirical investigation 26

547

(2018) 145–149\. URL: https://linkinghub.elsevier.com/retrieve/

548

pii/S1544612318300126. doi:10.1016/j.frl.2018.01.005.

549

\[3\] K. Liu, T. Weng, C. Gu, H. Yang,Visibility graph anal-

550

ysis ofbitcoin price series 538(2020)

122952\.

URL: https:

551

//linkinghub.elsevier.com/retrieve/pii/S0378437119316723.

552

doi:10.1016/j.physa.2019.122952.

24

T. Daudert, A multi-source entity-level sentiment corpus for the fi-

nancial domain: the finlin corpus, Language Resources and Evaluation

(2022). URL: https://link.springer.com/article/10.1007/s10579-

021-09555-3. doi:https://doi.org/10.1007/s10579-021-09555-3.

Jacobs, Gilles and Hoste, Veronique, SENTiVENT : enabling supervised

information extraction of company-specific events in economic and finan\-

cial news, LANGUAGE RESOURCES AND EVALUATION 56(2022)

225–257\. URL: http://dx.doi.org/10.1007/s10579-021-09562-4.

O.R.Meireles, G.Rosman, M.S. Altieri, L. Carin, G. Hager, A.Madani,

N.Padoy, C.M.Pugh, P.Sylla, T.M.Ward, D.A.Hashimoto, t.S.

V.A.forAI Working Groups, Sages consensus recommendations onan

annotation framework forsurgical video (2021).

J. Beck, R.  Huang, D. Lindner, T. Guo, C. Zhang, D. Helbing,

N. Antulov-Fantulin, Sensing social media signals for cryptocurrency

news, CoRR abs/1903.11451(2019). URL: http://arxiv.org/abs/

1903.11451\. arXiv:1903.11451.

J. Abraham, D.W. Higdon, J.Nelson, J.Ibarra, Cryptocurrency price

prediction using tweet volumes and sentiment analysis, 2018.

C.Lamon, E.Nielsen, E.Redondo, Cryptocurrency price prediction

using news and social media sentiment, 2017.

A.R.Khurshid, Cryptocurrency pricepredictionusing sentiment anal\-

ysis, 2021.

D. Ider, Cryptocurrency return prediction using investor sentiment ex-

tracted by bert-based classifiers from news articles, reddit posts and

tweets, ArXiv abs/2204.05781 (2022).

L.Ante, How elon musk’stwitter activity movescryptocurrency mar-

kets, Advertising & Marketing Law eJournal (2021).

L.Ante,How elon musk’stwitter activity moves cryptocurrency mar-

kets, SSRN ElectronicJournal (2022).

553

\[4\]

554

555

556

557

\[5\]

558

559

560

561

\[6\]

562

563

564

565

\[7\]

566

567

568

569

\[8\]

570

571

\[9\]

572

573

\[10\]

574

575

\[11\]

576

577

578

\[12\]

579

580

\[13\]

581

25

582

\[14\]Y.-S. Lee, R.Lo, C.-Y.Chen, P.-C. Lin, J.-C.Wang, News topics catego-

583

rization using latent dirichlet allocation and sparse representation clas-

584

sifier, in: 2015

IEEE

International Conference on Consumer Electronics

585

\- Taiwan, 2015, pp.136–137.doi:10.1109/ICCE-TW.2015.7216819\.

586

\[15\]Z.A.Guven, B.Diri, T.Cakaloglu,

Classification ofnew titles by

587

two stage latent dirichlet allocation, in: 2018Innovations inIntel-

588

ligent Systems  and Applications Conference  (ASYU), 2018,  pp. 1–5.

589doi:10.1109/ASYU.2018.8554027\.

590

\[16\] R. Adhitama, R. Kusumaningrum, R. Gernowo,Topic labeling to-

591wards news document collection based onlatent dirichlet allocation

592

and ontology, in: 20171stInternational Conference onInformatics

593

and Computational Sciences (ICICoS), 2017, pp. 247–252. doi:10.1109/

594

ICICOS.2017.8276370.

595

\[17\]

O.

K

¨

ose,

Crypto

asset

taxonom

y

classification

and

crypto

news

sen

ti-

596

ment analysis, Master’s thesis, Middle East Technical University, 2020.

597 \[18\]

S

ˇ

tefan

Ly

´

ocsa,

P

.

Moln

´

ar,

T.Pl´ıhal,

M.

S

ˇ

ira

n

ˇ

o

v

´

a,

Impact

598

of

macroeconomic

news,

regulation

and

hacking

exchange

599

markets onthe volatility ofbitcoin,Journal ofEconomic

600

Dynamics andControl 119(2020) 103980.URL: https://

601

www.sciencedirect.com/science/article/pii/S0165188920301482\.

602

doi:https://doi.org/10.1016/j.jedc.2020.103980.

603

\[19\] A.  H.  A.  Othman,  S.  M.  Alhabshi,  R.  Haron, The effect of

604

symmetric and asymmetric information on volatility structure of

605

crypto-currency markets,  Journal of Financial  Economic Policy  11

606

(2019) 432–450\. URL:https://doi.org/10.1108/JFEP-10-2018-0147.

607

doi:10.1108/JFEP-10-2018-0147.

608

\[20\] A. Klein,  L.  Kirilov, M. Riekert,  Cryptocurrency crashes:  A  dataset

609

formeasuring the effect ofregulatory news inonline media, in: Sys-

610

Risk@Wirtschaftsinformatik, 2019.

611

\[21\] I. Gurrib,  Q. L. Kweh,  M. Nourani, I. W. K. Ting,  Are cryptocurren-

612

cies affected bytheir asset class movements ornews announcements?,

613

Malaysian Journal of Economic Studies 56(2019) 201–225\. URL: https:

614

//search.informit.org/doi/10.3316/informit.815664021178630.

26

615

\[22\] T. V. H. Nguyen, B. T. Nguyen, K. S. Nguyen, H. Pham, Asymmetric

616

monetary policy effects oncryptocurrency markets, Research in

617

International Business and Finance 48 (2019) 335–339\. URL: https://

618

www.sciencedirect.com/science/article/pii/S0275531918310791.

619

doi:https://doi.org/10.1016/j.ribaf.2019.01.011.

620

\[23\] Z.  Liu, Finbert: A pre-trained  financial  language representation

621

model for  financial  text  mining, --(2020) 8.  URL:  -.  doi:https:

622

//www.researchgate.net/profile/Kei-Nakagawa-3/publication.

623

\[24\] E. L. Wong,  Prediction of Bitcoin prices using Twitter Data and Natu\-

624

ral Language Processing. (English), https://dukespace.lib.duke.edu/

625

dspace/bitstream/handle/10161/24081, 2020.

626

\[25\] K.  Leetaru, P. A.  Schrodt, Gdelt:  Global data on  events, lo-

627

cation, and  tone, ISA Annual  Convention (2013). URL: http://

628

citeseerx.ist.psu.edu/viewdoc/summary?doi=10.1.1.686.6605.

629

\[26\]Y. Finance, Yahoo finance, https://finance.yahoo.com/, 2022.

630

\[27\]

M.

F.

A.

Gadi,

M.

A

´

ngel

Sicilia,

Cryptolin

dataset

and

p

ython

ju

p

yter

631

notebooks reproducibilitycodes, https://github.com/manoelgadi/

632

CryptoLin IE, 2022.

633

\[28\]E.F.Fama, Efficient capital markets: a review oftheory andem\-

634

pirical work 25 (1970) 383–417\. URL: http://www.jstor.org/stable/

635

2325486\. doi:10.2307/2325486, publisher: \[American Finance Associa-\
\
636\
\
tion, Wiley\].

637

\[29\]

M.

F.

A.

Gadi,

M.

A

´

ngel

Sicilia,

Cryptolin

dataset

and

p

ython

jup

yter

638

notebooks reproducibilitycodes, https://github.com/manoelgadi/

639

CryptoGDelt2022, 2022.

640

\[30\] L. Yang, L. Li, Z. Zhang, X. Zhou, E. Zhou, Y. Liu, Dpgn: Distribution

641

propagation graph network for few-shot learning, 2020\. URL: https:

642

//arxiv.org/abs/2003.14247\. doi:10.48550/ARXIV.2003.14247.

643

\[31\]N. Zhang, L. Li, X. Chen, S. Deng, Z. Bi, C. Tan, F. Huang,

644

H. Chen, Differentiable prompt makes pre-trained language models bet-

645

ter few-shot learners, 2021. URL: https://arxiv.org/abs/2108.13161\.

646

doi:10.48550/ARXIV.2108.13161.

27

647

\[32\] C. Finn, P. Abbeel, S. Levine, Model-agnostic meta-learning for fast

648

adaptation of deep networks, 2017\. URL: https://arxiv.org/abs/

649

1703.03400\. doi:10.48550/ARXIV.1703.03400.

650

\[33\]J.Snell, K. Swersky, R. S. Zemel,

Prototypical networks for

651

few-shot learning, 2017\. URL: https://arxiv.org/abs/1703.05175.

652doi:10.48550/ARXIV.1703.05175\.

653

\[34\] T. B. Brown, B. Mann, N. Ryder, M. Subbiah, J. Kaplan, P. Dhariwal,

654

A.Neelakantan, P.Shyam, G.Sastry, A.Askell, S.Agarwal, A.Herbert-

655

Voss, G. Krueger, T. Henighan, R. Child, A. Ramesh, D. M. Ziegler,

656

J. Wu, C. Winter,  C. Hesse,  M. Chen, E. Sigler,  M. Litwin, S. Gray,

657

B. Chess, J. Clark, C. Berner, S. McCandlish, A. Radford, I. Sutskever,

658

D. Amodei, Language models are few-shot learners, 2020\. URL: https:

659

//arxiv.org/abs/2005.14165\. doi:10.48550/ARXIV.2005.14165.

660

\[35\] CoinMarketCal, Coinmarketcal crypto news, https://

661

coinmarketcal.com/en/news, 2022.

662

\[36\] J.R. Landis, G.G.Koch, Themeasurement ofobserver agreement for

663

categorical data, Biometrics 33(1977) 159\. URL: https://doi.org/

66410.2307/2529310. doi:10.2307/2529310.

665

\[37\] J.L.Fleiss, Measuring nominal scale agreement among many raters.,

666

Psychological Bulletin 76 (1971) 378–382\. URL: https://doi.org/

66710.1037/h0031619. doi:10.1037/h0031619.

668

\[38\] D. G. Altman, Practical statistics for medical research, CRC press,1990.

669

\[39\] D.V.Cicchetti, Guidelines, criteria,and rules ofthumb for evaluat\-

670

ing normed and standardized assessment instruments in psychology.,

671

Psychological Assessment 6 (1994) 284–290. URL: https://doi.org/

672

10.1037/1040-3590.6.4.284. doi:10.1037/1040-3590.6.4.284.

673

\[40\] S.Haghighi, M. Jasemi, S.Hessabi, Pycm : Multi class confusion matrix

674

library in python, 2018\. doi:10.5281/zenodo.1157173.

675

\[41\]C.Hutto, E.Gilbert, Vader-sentiment-analysis, https://github.com/

676

cjhutto/vaderSentiment, 2014.

28

{

677

\[42\]  S. Loria, Textblob sentiment analysis, https://github.com/sloria/

678

TextBlob, 2013.

679

\[43\] A.Akbik, Flair nlp library, https://github.com/flairNLP, 2019.

680

\[44\]B. O. G. O. T. F. R. SYSTEM, Money and Payments: The

681

U.S.Dollar in the Age of Digital Transformation. (English),

682

https://www.federalreserve.gov/publications/files/money-

683

and-payments-20220120.pdf, 2022.

684

\[45\] D.M.C.Coelho, Application oftheFama French 3-Factor model to

685

the  cryptocurrency and token markets, https://repositorio.ucp.pt/

686

bitstream/10400.14/31260/1/152417010, 2020.

687

\[46\] B.G.Teo, Estimating Stock Returns with Fama-French Three-Factor

688

Model in Python . (English), https://medium.com/the-handbook-

689

of-coding-in-finance/estimating-stock-returns-with-fama-

690

french-three-factor-model-in-python-1a98e3936859, 2021.

691

\[47\]K.R.French, Fama french data set, https://

692

mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-

693

F Research Data Factors daily CSV.zip, 2022.

694

6\. Annex

695

Setof best optimized hyper-parameters for the retrained FinBERT using

696

CryptoLinIE for Sentiment Score:

697

Model c o n f i g

BertConfig

698

” nameor path” : ”ProsusAI/ f i n b e r t ” ,

699

” a r c h i t e c t u r e s ” :

\[\
\
700\
\
”Ber t Fo r Seq u e n c e Clas s i f i c a t ion”\
\
701\] ,

702

” a tten t ion p rob s d rop o ut p rob ”:

0 . 1 ,

703

” c l a s s i f i e r d r o p o u t ”:

null,

704

” g r a d i e n t c h e ckpo int in g” :

f a l s e

,

705

” hiddenact”: ” gelu” ,

706

” hiddendropoutprob”:

0 . 1 ,

707

” h id d e n s i z e ” : 768 ,

29

{

}

{

}

708

” i d 2 l a b e l ”:

709

”0 ”: ” p o s i t i v e ” ,

710

”1 ”: ”negative” ,

711

”2 ”: ” n e u t ral ”

712

,

713

” i n i t i a l i z e r r a n g e ” : 0 . 0 2 ,

714

” i n t e r m e d i a t es i z e ” : 3072,

715

” l a b e l 2 i d ”:

716

”negat ive”: 1 ,

717

” n e u t ral ”:  2 ,

718

” p o s i t i v e ” : 0

719

,

720” layernormeps”: 1 e −12,

721” maxpositionembeddings” : 512 ,

722

” modeltype”: ”bert” ,

723

” numattentionheads” : 12 ,

724

” numhiddenlayers”: 12 ,

725

” padtokenid”: 0 ,

726

” positionembeddingtype” : ”a b s o lute” ,

727

”problemtype”: ” s i n g l e l a b e l c l a s s i f i c a t i o n ” ,

728

” torchdtype” : ” f l o a t 3 2 ” ,

729

” t r a n s f o r m e r s v e r s i o n ”: ” 4 . 2 0 . 0 ” ,

730

” typ e voc a b s i z e ”: 2 ,

731

” usecache”: true ,

732

”voc a b s i z e ” : 30522

733 }

... More specific tools implementing news aggregations and summarization in the cryptocurrency domain either produce or exploit sentiment analysis and relevance techniques to, for example, predict the price. Gadi et al. \[20\] introduced CryptoGDelt2022, a dataset generated by extracting news event from the Global Database of Events, Language and Tone (GDELT), including 243,422 rows and 19 columns. The cryptocurrency corpus was used to extract valuable statistics with regard to relevance, sentiments, and strength (i.e., the impact that news may have). ...

... The developed application aims to be the starting point for an integrated crypto news processing tool that can be extended in the future with several different features, such as a framework for correlating cryptocurrency prices to news sentiment reported by major online news outlets. With regard to \[20,21\], Cryptoblend explicitly focuses on the aggregation and summarization of financial news in the cryptocurrency domain. ...

[Cryptoblend: An AI-Powered Tool for Aggregation and Summarization of Cryptocurrency News](https://www.researchgate.net/publication/366944318_Cryptoblend_An_AI-Powered_Tool_for_Aggregation_and_Summarization_of_Cryptocurrency_News)

Article

Full-text available

- Jan 2023

- [![Andrea Pozzi](https://i1.rgstatic.net/ii/profile.image/700416694185985-1544003761128_Q64/Andrea-Pozzi-2.jpg)\\
Andrea Pozzi](https://www.researchgate.net/profile/Andrea-Pozzi-2)
- [![Enrico Barbierato](https://i1.rgstatic.net/ii/profile.image/287715988918272-1445608245060_Q64/Enrico-Barbierato.jpg)\\
Enrico Barbierato](https://www.researchgate.net/profile/Enrico-Barbierato)
- [![Daniele Toti](https://i1.rgstatic.net/ii/profile.image/11431281151141810-1681946229793_Q64/Daniele-Toti.jpg)\\
Daniele Toti](https://www.researchgate.net/profile/Daniele-Toti)

In the last decade, the techniques of news aggregation and summarization have been increasingly gaining relevance for providing users on the web with condensed and unbiased information. Indeed, the recent development of successful machine learning algorithms, such as those based on the transformers architecture, have made it possible to create effective tools for capturing and elaborating news from the Internet. In this regard, this work proposes, for the first time in the literature to the best of the authors’ knowledge, a methodology for the application of such techniques in news related to cryptocurrencies and the blockchain, whose quick reading can be deemed as extremely useful to operators in the financial sector. Specifically, cutting-edge solutions in the field of natural language processing were employed to cluster news by topic and summarize the corresponding articles published by different newspapers. The results achieved on 22,282 news articles show the effectiveness of the proposed methodology in most of the cases, with 86.8% of the examined summaries being considered as coherent and 95.7% of the corresponding articles correctly aggregated. This methodology was implemented in a freely accessible web application.

[View](https://www.researchgate.net/publication/366944318_Cryptoblend_An_AI-Powered_Tool_for_Aggregation_and_Summarization_of_Cryptocurrency_News)

Show abstract

[SENTiVENT: Enabling Supervised Information Extraction of Company-Specific Events in Economic and Financial News](https://www.researchgate.net/publication/354573583_SENTiVENT_Enabling_Supervised_Information_Extraction_of_Company-Specific_Events_in_Economic_and_Financial_News)

Article

Full-text available

- Mar 2022

- [![Gilles Jacobs](https://i1.rgstatic.net/ii/profile.image/583787930992641-1516197297563_Q64/Gilles-Jacobs.jpg)\\
Gilles Jacobs](https://www.researchgate.net/profile/Gilles-Jacobs)
- [![Véronique Hoste](https://i1.rgstatic.net/ii/profile.image/989582002765829-1612946143673_Q64/Veronique-Hoste.jpg)\\
Véronique Hoste](https://www.researchgate.net/profile/Veronique-Hoste)

We present SENTiVENT, a corpus of fine-grained company-specific events in English economic news articles. The domain of event processing is highly productive and various general domain, fine-grained event extraction corpora are freely available but economically-focused resources are lacking. This work fills a large need for a manually annotated dataset for economic and financial text mining applications. A representative corpus of business news is crawled and an annotation scheme developed with an iteratively refined economic event typology. The annotations are compatible with benchmark datasets (ACE/ERE) so state-of-the-art event extraction systems can be readily applied. This results in a gold-standard dataset annotated with event triggers, participant arguments, event co-reference, and event attributes such as type, subtype, negation, and modality. An adjudicated reference test set is created for use in annotator and system evaluation. Agreement scores are substantial and annotator performance adequate, indicating that the annotation scheme produces consistent event annotations of high quality. In an event detection pilot study, satisfactory results were obtained with a macro-averaged F1-score of 59% validating the dataset for machine learning purposes. This dataset thus provides a rich resource on events as training data for supervised machine learning for economic and financial applications. The dataset and related source code is made available at https://osf.io/8jec2/.

[View](https://www.researchgate.net/publication/354573583_SENTiVENT_Enabling_Supervised_Information_Extraction_of_Company-Specific_Events_in_Economic_and_Financial_News)

Show abstract

[Cryptocurrency Crashes: A Dataset for Measuring the Effect of Regulatory News in Online Media](https://www.researchgate.net/publication/339626804_Cryptocurrency_Crashes_A_Dataset_for_Measuring_the_Effect_of_Regulatory_News_in_Online_Media)

Conference Paper

Full-text available

- Feb 2019

- [![Achim Klein](https://i1.rgstatic.net/ii/profile.image/449342025801730-1484142895832_Q64/Achim-Klein.jpg)\\
Achim Klein](https://www.researchgate.net/profile/Achim-Klein)
- [![Lyubomir Kirilov](https://c5.rgstatic.net/m/4671872220764/images/template/default/profile/profile_default_m.jpg)\\
Lyubomir Kirilov](https://www.researchgate.net/profile/Lyubomir-Kirilov)
- [![Martin Riekert](https://i1.rgstatic.net/ii/profile.image/375752114622467-1466597693449_Q64/Martin-Riekert.jpg)\\
Martin Riekert](https://www.researchgate.net/profile/Martin-Riekert)

Cryptocurrencies are novel means for transacting value, promising lower transaction costs and a complete transaction history, which cannot be manipulated. Systematic risks to such transaction systems are posed by regulatory actions that put strong restrictions on usage-up to complete bans of cryptocur-rencies. Prior research has studied the effect of regulatory news on cryptocurrency pricing and found price effects of news of regulatory actions of authorities. We propose a novel dataset of news from online media that loosely relates to cryptocurrency regulation, but includes also opinions and rumors. The proposed dataset allows to study drivers of crashes and risks in cryptocurrency markets.

[View](https://www.researchgate.net/publication/339626804_Cryptocurrency_Crashes_A_Dataset_for_Measuring_the_Effect_of_Regulatory_News_in_Online_Media)

Show abstract

[Are Cryptocurrencies Affected by Their Asset Class Movements or News Announcements?](https://www.researchgate.net/publication/337736986_Are_Cryptocurrencies_Affected_by_Their_Asset_Class_Movements_or_News_Announcements)

Article

Full-text available

- Dec 2019

- [Ikhlaas Gurrib](https://www.researchgate.net/scientific-contributions/Ikhlaas-Gurrib-80885992)
- [Qian Long Kweh](https://www.researchgate.net/scientific-contributions/Qian-Long-Kweh-2044181919)
- [![Pedram Nourani](https://i1.rgstatic.net/ii/profile.image/11431281201419741-1698389005724_Q64/Pedram-Nourani.jpg)\\
Pedram Nourani](https://www.researchgate.net/profile/Pedram-Nourani)
- [![Irene Wei Kiong Ting](https://i1.rgstatic.net/ii/profile.image/322690844430337-1453946900411_Q64/Irene-Ting-2.jpg)\\
Irene Wei Kiong Ting](https://www.researchgate.net/profile/Irene-Ting-2)

This study analyses whether returns of top market capitalised cryptocurrencies are affected by their movements or major global macroeconomic news. Daily data are collected for the leading 10 cryptocurrencies from July 2017–December 2018. This study, (i) tests whether lagged variables can help predict other variables’ returns through a vector autoregression (VAR) model, (ii) analyses the response of cryptocurrencies to one standard deviation shock on Bitcoin’s returns, and (iii) decomposes factors that contribute to variance and tests for structural breaks. Findings show that most cryptocurrencies do not significantly affect other variances, except for Monero, which represented between 19% and 45% of the variances of five cryptocurrencies. Autoregressive (AR) models are superior in forecasting one day ahead return forecasts, compared to the VAR model, whereas the random walk (RW) model ranked last. Although remarkable structural breaks are observed via impulse response functions during December 2017–January 2018, no major news announcements were released on the same day the breaks occurred. Overall, this study suggests the need for high-frequency cryptocurrency prices to tackle the issue of the relationship between intraday news release and cryptocurrencies.

[View](https://www.researchgate.net/publication/337736986_Are_Cryptocurrencies_Affected_by_Their_Asset_Class_Movements_or_News_Announcements)

Show abstract

[Sensing Social Media Signals for Cryptocurrency News](https://www.researchgate.net/publication/333071850_Sensing_Social_Media_Signals_for_Cryptocurrency_News)

Conference Paper

Full-text available

- May 2019

- [Johannes Beck](https://www.researchgate.net/scientific-contributions/Johannes-Beck-2155312668)
- [Roberta Huang](https://www.researchgate.net/scientific-contributions/Roberta-Huang-2155316288)
- [David Lindner](https://www.researchgate.net/scientific-contributions/David-Lindner-2155298887)
- [![Nino Antulov-Fantulin](https://i1.rgstatic.net/ii/profile.image/978394804154368-1610278907000_Q64/Nino-Antulov-Fantulin.jpg)\\
Nino Antulov-Fantulin](https://www.researchgate.net/profile/Nino-Antulov-Fantulin)

The ability to track and monitor relevant and important news in real-time is of crucial interest in multiple industrial sectors. In this work, we focus on cryptocurrency news, which recently became of emerging interest to the general and financial audience. In order to track popular news in real-time, we (i) match news from the web with tweets from social media, (ii) track their intraday tweet activity and (iii) explore different machine learning models for predicting the number of article mentions on Twitter after its publication. We compare several machine learning models, such as linear extrapolation, linear and random forest autoregressive models, and a sequence-to-sequence neural network.

[View](https://www.researchgate.net/publication/333071850_Sensing_Social_Media_Signals_for_Cryptocurrency_News)

Show abstract

[How Elon Musk's Twitter Activity Moves Cryptocurrency Markets](https://www.researchgate.net/publication/359461336_How_Elon_Musk's_Twitter_Activity_Moves_Cryptocurrency_Markets)

Article

- Jan 2022

- [![Lennart Ante](https://i1.rgstatic.net/ii/profile.image/725145861758977-1549899654233_Q64/Lennart-Ante.jpg)\\
Lennart Ante](https://www.researchgate.net/profile/Lennart-Ante)

[View](https://www.researchgate.net/publication/359461336_How_Elon_Musk's_Twitter_Activity_Moves_Cryptocurrency_Markets)

[FinBERT: A Pre-trained Financial Language Representation Model for Financial Text Mining](https://www.researchgate.net/publication/342793634_FinBERT_A_Pre-trained_Financial_Language_Representation_Model_for_Financial_Text_Mining)

Conference Paper

- Jul 2020

- [![Zhuang Liu](https://i1.rgstatic.net/ii/profile.image/583823658074112-1516205815261_Q64/Zhuang-Liu-14.jpg)\\
Zhuang Liu](https://www.researchgate.net/profile/Zhuang-Liu-14)
- [![Degen Huang](https://i1.rgstatic.net/ii/profile.image/1060627078467584-1629884609165_Q64/Degen-Huang.jpg)\\
Degen Huang](https://www.researchgate.net/profile/Degen-Huang)
- [![Huang Kaiyu](https://c5.rgstatic.net/m/4671872220764/images/template/default/profile/profile_default_m.jpg)\\
Huang Kaiyu](https://www.researchgate.net/profile/Huang-Kaiyu)
- [Jun Zhao](https://www.researchgate.net/scientific-contributions/Jun-Zhao-2199267121)

There is growing interest in the tasks of financial text mining. Over the past few years, the progress of Natural Language Processing (NLP) based on deep learning advanced rapidly. Significant progress has been made with deep learning showing promising results on financial text mining models. However, as NLP models require large amounts of labeled training data, applying deep learning to financial text mining is often unsuccessful due to the lack of labeled training data in financial fields. To address this issue, we present FinBERT (BERT for Financial Text Mining) that is a domain specific language model pre-trained on large-scale financial corpora. In FinBERT, different from BERT, we construct six pre-training tasks covering more knowledge, simultaneously trained on general corpora and financial domain corpora, which can enable FinBERT model better to capture language knowledge and semantic information. The results show that our FinBERT outperforms all current state-of-the-art models. Extensive experimental results demonstrate the effectiveness and robustness of FinBERT. The source code and pre-trained models of FinBERT are available online.

[View](https://www.researchgate.net/publication/342793634_FinBERT_A_Pre-trained_Financial_Language_Representation_Model_for_Financial_Text_Mining)

Show abstract

[Visibility graph analysis of Bitcoin price series](https://www.researchgate.net/publication/336081265_Visibility_graph_analysis_of_Bitcoin_price_series)

Article

- Sep 2019
- PHYSICA A

- [Keshi Liu](https://www.researchgate.net/scientific-contributions/Keshi-Liu-2164122725)
- [Tongfeng Weng](https://www.researchgate.net/scientific-contributions/Tongfeng-Weng-2041119092)
- [![Changgui Gu](https://i1.rgstatic.net/ii/profile.image/273679271591939-1442261631218_Q64/Changgui-Gu.jpg)\\
Changgui Gu](https://www.researchgate.net/profile/Changgui-Gu)
- [![Huijie Yang](https://c5.rgstatic.net/m/4671872220764/images/template/default/profile/profile_default_m.jpg)\\
Huijie Yang](https://www.researchgate.net/profile/Huijie-Yang-2)

The Bitcoin market attracts special attentions for its inspirational advantages over the traditional currency system. It can be regarded also as a typical social experiment of rare item markets. Analyzing the records for Bitcoin price can deepen our understanding of this market and provide us a useful reference for rare item markets. In this paper, by means of the visibility graph algorithm we display multi-scale patterns of visible relationships in Bitcoin volatility series. It is found that the visibility graph of Bitcoin is scale-free and has a hierarchical structure. At different time scales, the system works subsequently with an identical dynamical mechanism. These behaviors are shared by other virtual currencies and even the gold price series.

[View](https://www.researchgate.net/publication/336081265_Visibility_graph_analysis_of_Bitcoin_price_series)

Show abstract

[Asymmetric Monetary Policy Effects on Cryptocurrency Markets](https://www.researchgate.net/publication/330661466_Asymmetric_Monetary_Policy_Effects_on_Cryptocurrency_Markets)

Article

- Jan 2019
- Res Int Bus Finance

- [![Thai Nguyen](https://i1.rgstatic.net/ii/profile.image/362634642771974-1463470244858_Q64/Thai-Nguyen-8.jpg)\\
Thai Nguyen](https://www.researchgate.net/profile/Thai-Nguyen-8)
- [![Binh Nguyen Thanh](https://i1.rgstatic.net/ii/profile.image/730395112902658-1551151173521_Q64/Binh-Nguyen-Thanh-4.jpg)\\
Binh Nguyen Thanh](https://www.researchgate.net/profile/Binh-Nguyen-Thanh-4)
- [![Kien Son Nguyen](https://i1.rgstatic.net/ii/profile.image/1130006797393927-1646426023620_Q64/Kien-Nguyen-15.jpg)\\
Kien Son Nguyen](https://www.researchgate.net/profile/Kien-Nguyen-15)
- [![Huy Pham](https://i1.rgstatic.net/ii/profile.image/592896440942592-1518368935468_Q64/Huy-Pham-9.jpg)\\
Huy Pham](https://www.researchgate.net/profile/Huy-Pham-9)

[View](https://www.researchgate.net/publication/330661466_Asymmetric_Monetary_Policy_Effects_on_Cryptocurrency_Markets)

[Does Economic Policy Uncertainty Predict the Bitcoin Returns? An Empirical Investigation](https://www.researchgate.net/publication/322825321_Does_Economic_Policy_Uncertainty_Predict_the_Bitcoin_Returns_An_Empirical_Investigation)

Article

- Jan 2018

- [![Ender Demir](https://i1.rgstatic.net/ii/profile.image/329423493582849-1455552089521_Q64/Ender-Demir.jpg)\\
Ender Demir](https://www.researchgate.net/profile/Ender-Demir)
- [Giray Gozgor](https://www.researchgate.net/scientific-contributions/Giray-Gozgor-2028502600)
- [![Chi Keung Marco Lau](https://i1.rgstatic.net/ii/profile.image/277503122919435-1443173308737_Q64/Chi-Keung-Lau.jpg)\\
Chi Keung Marco Lau](https://www.researchgate.net/profile/Chi-Keung-Lau)
- [Samuel A. Vigne](https://www.researchgate.net/scientific-contributions/Samuel-A-Vigne-2346764002)

This paper analyzes the prediction power of the economic policy uncertainty (EPU) index on the daily Bitcoin returns. Using the Bayesian Graphical Structural Vector Autoregressive model as well as the Ordinary Least Squares and the Quantile-on-Quantile Regression estimations, the paper finds that the EPU has a predictive power on Bitcoin returns. Fundamentally, Bitcoin returns are negatively associated with the EPU. However, the effect is positive and significant at both lower and higher quantiles of Bitcoin returns and the EPU. In the light of these findings, the paper concludes that Bitcoin can serve as a hedging tool against uncertainty.

[View](https://www.researchgate.net/publication/322825321_Does_Economic_Policy_Uncertainty_Predict_the_Bitcoin_Returns_An_Empirical_Investigation)

Show abstract

[Prototypical Networks for Few-shot Learning](https://www.researchgate.net/publication/315096921_Prototypical_Networks_for_Few-shot_Learning)

Article

- Mar 2017

- [Jake Snell](https://www.researchgate.net/scientific-contributions/Jake-Snell-2252475930)
- [Kevin Swersky](https://www.researchgate.net/scientific-contributions/Kevin-Swersky-80786093)
- [![Richard Zemel](https://c5.rgstatic.net/m/4671872220764/images/template/default/profile/profile_default_m.jpg)\\
Richard Zemel](https://www.researchgate.net/profile/Richard-Zemel)

We propose prototypical networks for the problem of few-shot classification, where a classifier must generalize to new classes not seen in the training set, given only a small number of examples of each new class. Prototypical networks learn a metric space in which classification can be performed by computing Euclidean distances to prototype representations of each class. Compared to recent approaches for few-shot learning, they reflect a simpler inductive bias that is beneficial in this limited-data regime, and achieve state-of-the-art results. We provide an analysis showing that some simple design decisions can yield substantial improvements over recent approaches involving complicated architectural choices and meta-learning. We further extend prototypical networks to the case of zero-shot learning and achieve state-of-the-art zero-shot results on the CU-Birds dataset.

[View](https://www.researchgate.net/publication/315096921_Prototypical_Networks_for_Few-shot_Learning)

Show abstract

Show more