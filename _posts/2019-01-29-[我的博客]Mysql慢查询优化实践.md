
### Mysql 慢查询优化实践
![](https://i.loli.net/2019/01/29/5c500da77dc76.jpg)


###### 目标:
提高mysql运行效率,增加并发,提高响应速度

###### 方案:
通过阿里云给的慢查询日志excel,对耗时长,开销大的sql语句进行优化,提升访问速度服务器运行效率

###### 实践:


分析
阿里云给的数据库单日报表有以下字段
- Create Time	DBName	
- MySQL Total Execution Counts	
- MySQL Total Execution Times	
- Max Execution Time	
- Max Lock Time	
- Parse Total Row Counts
- Parse Max Row Count	
- Return Total Row Counts
- Return Max Row Count	
- SQL Text
- hard ware- latencies
 
分别是 

- 创建时间
- 数据库名
- mysql总执行数目
- muysql总执行耗时
- 最大执行耗时
- 最大锁耗时
- 解析总行数统计
- 解析最大行数
- 返回总计行数
- 返回最大行数
- sql语句
- 硬件延迟

根据阿里云提供的慢查询记录,本次采用的优化策略如下:

查询次数超过100次/日的高频需求,按照最大查询/总查询用时最大,依次优化取得的优化收益最高.

##### 第一条语句:
执行次数: 1114 最大耗时: 7 解析最大行数: 348325  返回最大行数 4
#执行次数: 1114 最大耗时: 7 解析最大行数: 348325  返回最大行数 4


```
select id from appname_m_members where yiku_id = :1
```



可以看出,这个简单的sql不应该有这么大的解析行数,甚至最高要七秒钟.<br>
初步判断没有在yiku_id这个字段加索引的可能性最大.现在我们需要寻求各种办法来验证下我们的猜测

###### 分析

```
explain select id from appname_m_members where yiku_id = 1;
```

![](https://i.loli.net/2019/01/29/5c4ffa3dbeadc.png)




可以看到的确是没有给yiku_id增加索引.

索引的特点<br>
对于查询操作能迅速缩小查询范围,减少row的数量,指数级提高查询速度点<br>
对于写操作,因为需要维护索引的变更,有一定开销.如果遇到大量并发写入,会有负面影响.<br>
在这个表用来记录我们微信用户和应用id的关系,所以读的操作较之写操作更多,所以能够增加索引.<br>

```
#增加索引

ALTER TABLE `appname_m_members` 
ADD INDEX `yiku_id` (`yiku_id`) ;
```


尝试增加索引之后,再次分析语句的执行

![](https://i.loli.net/2019/01/29/5c4ffa9f1d4e4.png)


###### 结果:
匹配范围 rows 从32w 降低到1

可以看到type从all的全表扫描变成ref的单个行的索引访问,rows从全表32w降为1,说明添加索引对这条语句产生了巨大效果.





##### 第二条语句:
执行次数: 482 最大耗时: 15 解析最大行数: 764383 返回最大行数: 482


```
#执行次数: 482 最大耗时: 15 解析最大行数: 764383 返回最大行数: 482
select fullname as username , linkphone as userphone , 
`userimage` , `nickname` , `hospitalname` , `partmentname` , 
`doctortitle` , `iscertification` , `fullname` 
from `users` 
where `useruuid` = '597_f66e1cb79341cedf6f24aaf01fde8611' limit 1;
```



###### 分析:

![](https://i.loli.net/2019/01/29/5c4ffb0c12a79.png)



###### 对其增加索引:


```
#增加索引
ALTER TABLE `users` 
ADD INDEX `useruuid` (`useruuid`);
```


![](https://i.loli.net/2019/01/29/5c4ffb2a54856.png)



直接将扫描范围(rows)从72w降到了1,提升明显

###### 结果:
匹配范围 rows 从72w 降低到1


##### 第三条语句:
执行次数: 820 最大耗时: 10 解析最大行数: 167214  返回最大行数 1

```
#执行次数: 820 最大耗时: 10 解析最大行数: 167214  返回最大行数 1
select count ( postingid ) as postnum from mediposting 
where isaudit != :1
and isgoodcase = :2
and postsection = :3
```



###### 分析:

![](https://i.loli.net/2019/01/29/5c4ffb91aa0d5.png)


改变sql语句的顺序,按照最左原则修改如下


```
select count(postingid) as postnum from mediposting 
where postsection = 1
and isgoodcase = 1
and isaudit != 1
```





###### 结果:

主要使用的是 postsection 作为索引来统计总数,这部分无需优化.


```
##### 第四条语句:
执行次数: 482 最大耗时: 15 解析最大行数: 764383 返回最大行数: 482
##执行次数: 410 最大耗时: 10 解析最大行数:348325   返回最大行数 1
........
```



###### 结果: 语句过长(2017个字符),嵌套了逻辑,暂不优化

##### 第五条语句:

执行次数: 659 最大耗时: 6 解析最大行数:215115   返回最大行数 659

```
## 执行次数: 659 最大耗时: 6 解析最大行数:215115   返回最大行数 659
select `medigooddoc`.`docid` , `medigooddoc`.`docname` ,
 `medigooddoc`.`doctitle` , `medigooddoc`.`docimgurl` ,
  `medigooddoc`.`docdep` , `medigooddoc`.`dochospital` ,
   ( initalscore+effectevaladd ) as `effectval` 
   from `medigooddoc` 
   where ( ( initalscore+effectevaladd ) > 80 ) 
   order by rand ( ) limit 1 ;
```



###### 分析:

rand()函数放在order by后面会被执行多次,优化方式:
求出随机id后,取得对应记录

```
select `medigooddoc`.`docid` , `medigooddoc`.`docname` ,
 `medigooddoc`.`doctitle` , `medigooddoc`.`docimgurl` ,
 `medigooddoc`.`docdep` , `medigooddoc`.`dochospital` ,
 ( initalscore+effectevaladd ) as `effectval` 
 from `medigooddoc` 
 where (initalscore+effectevaladd)  > 80
 and docid > ( 
     RAND() * (
         (SELECT MAX(docid) FROM `medigooddoc`) 
         -
         (SELECT MIN(docid) FROM `medigooddoc`)
    )
    +
    (SELECT MIN(docid) FROM `medigooddoc`) 
 )
 order by `docid` limit 1;
```



优化前语句:

![](https://i.loli.net/2019/01/29/5c4ffc06d510e.png)


可以看到扫描范围很大(rows) 120 770行.

![](https://i.loli.net/2019/01/29/5c4ffc20b3aa5.png)

可以看到
- 查询范围最小(rows) 1
- 获取最大值/最小值是直接从mysql查询优化器返回数据(extra).mysql文档中有以下解释:
> The query contained only aggregate functions (MIN(), MAX()) that were all resolved using an index, or COUNT(*) for MyISAM, and no GROUP BY clause. The optimizer determined that only one row should be returned.
> 
测试执行效率:
- 执行10次	a:   2 941 ms 	b:    168 ms	
- 执行50次	a: 14 441 ms	b:    828 ms
- 执行100次a: 29 126 ms	b: 1 645 ms 

可以看到每百次运行时间已经从30s缩短到不到2秒,大大提高查询mysql响应速度.
但是还有个问题,总共100 000的id,原来的语句查询出的结果比较平衡,有过万也有几千,但是用这个语句后,总是出现小于一万的id,结果在我们预期之外.

修正概率偏差

###### 方案1: 
增加一次对数据库消耗不大的表查询

```
# php
$round = select max(docid) as max,min(docid) as min from medigooddoc;
$rand = rand($round['min'],$round['max']);
```


```
# sql
select `medigooddoc`.`docid` , `medigooddoc`.`docname` ,
 `medigooddoc`.`doctitle` , `medigooddoc`.`docimgurl` ,
 `medigooddoc`.`docdep` , `medigooddoc`.`dochospital` ,
 ( initalscore+effectevaladd ) as `effectval` 
 from `medigooddoc` 
 where (initalscore+effectevaladd)  > 80
 and docid > $rand
 order by `docid` limit 1;
```


这样的问题是:会多产生一个sql交互,数据库

###### 方案2:
使用内连接 join 优化


```
#可用一
select `docid` ,`docname`,
 `doctitle` , `docimgurl` ,
 `docdep` , `dochospital` ,
 ( initalscore+effectevaladd ) as `effectval` 
 from `medigooddoc` as t1 
 join (
     select rand() * (select max(docid) from `medigooddoc`) 
     as rand
 ) as t2 
 where (t1.initalscore+t1.effectevaladd)  > 80
 and `t1`.`docid` >= t2.rand
 order by `docid` limit 1;
```



但是这样有一个问题:并不是完全平均落到每条记录上,因为记录并不是连续的

 修正概率 rand * 数量范围,这样概率平均到整张表存在的记录中.


```
select `docid` ,`docname`,
 `doctitle` , `docimgurl` ,
 `docdep` , `dochospital` ,
 ( initalscore+effectevaladd ) as `effectval` 
 from `medigooddoc` as t1 
 join (
     select rand() * 
     (
         (select max(docid) from `medigooddoc`)
         -
         (select min(docid) from `medigooddoc`)
     )
     +
     (select min(docid) from `medigooddoc`)  
     as rand
 ) as t2 
 where (t1.initalscore+t1.effectevaladd)  > 80
 and `t1`.`docid` >= t2.rand
 order by `docid` limit 1;
```



综合来说,因为方案1 产生了更多的数据库交互,因为我们的数据库是另一台服务器,网络连接开销是比较大的,额外的查询也会在高并发的时刻对数据库产生更大压力.

而方案2采用内连接的方式,仅需要一次数据库交互就能完成,最大最小值也是直接由mysql查询器返回,减少了种种数据库性能开销.故采用为最佳方案..

![](https://i.loli.net/2019/01/29/5c4ffce3af4ad.png)



###### 结果:
使用mysql保存的表结构信息替代了order rand()的低效率查询.

###### 深入理解:

![](https://i.loli.net/2019/01/29/5c4ffcf5e9dab.png)




##### 第六条语句:
执行次数: 729 最大耗时: 4秒 解析最大行数:130898   返回最大行数 2


```
select `medigooddoc`.`docid` , `medigooddoc`.`yikuid` 
from `medigooddoc` 
where ( yikuid = 597725 or yikuid = -597725 );
```



###### 分析:

![](https://i.loli.net/2019/01/29/5c4ffd1fe2bdf.png)


###### 优化方案: 
字段`yikuid`加索引


```
ALTER TABLE `medigooddoc`
ADD INDEX `YiKuID` (`YiKuID`);
```



再次执行explain分析

![](https://i.loli.net/2019/01/29/5c4ffd65b37a2.png)


###### 结果: 
匹配范围 rows 从8.3w 降低到1


##### 第七条语句
执行次数: 474 最大耗时: 5秒 解析最大行数:261797   返回最大行数 1


```
select `medigooddoc`.`docid` , `medigooddoc`.`docname` ,
 `medigooddoc`.`doctitle` , `medigooddoc`.`docimgurl` 
 from `medigooddoc` order by rand ( ) limit 1;
```



###### 分析

![](https://i.loli.net/2019/01/29/5c5007ba65645.png)


###### 方案 
将获取一条随机记录 由order by rand() limit 1 改为 内连接方式


```
select `docid`, `docname`,
  `doctitle` , `docimgurl` 
 from `medigooddoc` as  t1 
 inner join 
 (
     select rand()  *
     (
         (select MAX(docid) from `medigooddoc`)
         -
         (select MIN(docid) from `medigooddoc`)
     )
     +
     (select MIN(docid) from `medigooddoc`)
     as rand
 ) as t2 
 on t1.docid >= t2.rand
 order by docid limit 1;
```


再次执行explain分析

![](https://i.loli.net/2019/01/29/5c5007d8ad139.png)


###### 结果
用mysql存储的表信息替代了效率低下的order by rand()


##### 第八条语句
执行次数: 136 最大耗时: 7秒 解析最大行数:301880   返回最大行数 1


```
select `searchrecords`.`searchid` , `searchrecords`.`searchnum` 
from `searchrecords` 
where ( searchtype = 0 ) and ( userid = 14 ) 
and ( searchmsg = '碳酸钙D3' );
```


###### 分析

![](https://i.loli.net/2019/01/29/5c5007fccb429.png)


###### 方案
索引的目的是为了缩小查询范围,通过文字内容的前三个字区分,通过userid进行区分,可以得到范围更精确的语句执行


```
ALTER TABLE searchrecords ADD INDEX searchmsg (searchmsg(5));
ALTER TABLE searchrecords ADD INDEX userid (userid);
```



通过文本前5个字建立索引来区分范围后,范围缩小到28个记录

![](https://i.loli.net/2019/01/29/5c50081a14ba6.png)


再通过用户ID建立索引,进一步缩小范围,仅需要查找1条记录

![](https://i.loli.net/2019/01/29/5c5008900dca9.png)


分析索引对写入的影响
表主要用来记录用户搜索的高频词,主要的写操作时更新统计字段,这两个新增索引的字段并不会频繁更新,故索引开销不大.

###### 结果
匹配范围从 29w 缩小到 1

##### 第九条语句 

```
select `projects`.`id` , `projects`.`guid` , 
`projects`.`getittime` , `projects`.`keywords` ,
 `projects`.`barcode` as `num` , `projects`.`goodcasedep` ,
  `projects`.`bingshi` , `pictures`.* 
  from `projects` 
  inner join `pictures` on projects.guid = pictures.projectid 
  and pictures.filetype = :1 
  where ( islock != :2 ) and ( isgoodcase = :3 ) 
  and ( ( goodcasedep like :4 or goodcasedep like :5 
  or goodcasedep like :6 or goodcasedep like :7 
  or goodcasedep like :8 or goodcasedep like :9 
  or goodcasedep like :10 or goodcasedep like :11 
  or goodcasedep like :12 or goodcasedep like :13 
  or goodcasedep like :14 or goodcasedep like :15 
  or goodcasedep like :16 or goodcasedep like :17 
  or goodcasedep like :18 or goodcasedep like :19 
  or goodcasedep like :20 or goodcasedep like :21 
  or goodcasedep like :22 or goodcasedep like :23 
  or goodcasedep like :24 or goodcasedep like :25 
  or goodcasedep like :26 or goodcasedep like :27 
  or goodcasedep like :28 or goodcasedep like :29 
  or goodcasedep like :30 or goodcasedep like :31 
  or goodcasedep like :32 or goodcasedep like :33 
  or goodcasedep like :34 or goodcasedep like :35 
  or goodcasedep like :36 or goodcasedep like :37 
  or goodcasedep like :38 or goodcasedep like :39 
  or goodcasedep like :40 or goodcasedep like :41 ) ) 
  order by rand ( ) limit :42
```



###### 结果:
暂不修改:超过字节限制

##### 第十条语句
执行次数: 145 最大耗时: 2秒 解析最大行数:130898   返回最大行数 1


```
select `medigooddoc`.`isfollow` , `medigooddoc`.`isconsult` ,
 `medigooddoc`.`isphone` , `medigooddoc`.`isprivate` 
 from `medigooddoc` where ( yikuid =  694 );
```


###### 分析:

![](https://i.loli.net/2019/01/29/5c5008d02329c.png)


###### 方案
增加索引


```
ALTER TABLE `medigooddoc` ADD INDEX YiKuID(`YiKuID`);
```



再次执行explain分析

![](https://i.loli.net/2019/01/29/5c5008efd6552.png)


###### 结果
匹配范围从12w缩小到1


##### 第十一条
执行次数: 148 最大耗时: 3秒 解析最大行数:74616   返回最大行数 30


```
select `magazinearticle`.`articleid` , 
`magazinearticle`.`articletitle` , 
`magazinearticle`.`article_publishtime` ,
 `magazinearticle`.`articlepicpath` ,
  `magazinearticle`.`articleurl` ,
   `magazinearticle`.`articlenum` ,
    `magazinearticle`.`perid` ,
     `magazinearticle`.`article_originallink` ,
      `magazinearticle`.`islink` from `magazinearticle` 
      where ( logicdel = 0 ) and ( perid != 60 ) 
      order by `article_publishtime` desc limit 1,30;
```


###### 分析:

![](https://i.loli.net/2019/01/29/5c5009235c3cf.png)


###### 方案:

由于是读多写少的文章表,增加索引适用这类场景,提高查询响应速度.


```
ALTER TABLE `magazinearticle` ADD INDEX 
article_publishtime(`article_publishtime`);
```



再次执行explain分析

![](https://i.loli.net/2019/01/29/5c50093914529.png)


###### 结果:
匹配范围 rows 从2w缩小到59


###### 深入理解:

explain type的不同种类

类型 | 含义
---|---
类型	| 含义
system	| 表只有一行
const	| 表最多只有一行匹配，通用用于主键或者唯一索引比较时
eq_ref	| 每次与之前的表合并行都只在该表读取一行，这是除了system，const之外最好的一种，特点是使用=，而且索引的所有部分都参与join且索引是主键或非空唯一键的索引
ref	| 如果每次只匹配少数行，那就是比较好的一种，使用=或<=>，可以是左覆盖索引或非主键或非唯一键
fulltext	| 全文搜索
ref_or_null	| 与ref类似，但包括NULL
index_merge	| 表示出现了索引合并优化(包括交集，并集以及交集之间的并集)，但不包括跨表和全文索引。<br>这个比较复杂，目前的理解是合并单表的范围索引扫描（如果成本估算比普通的range要更优的话)
unique_subquery	| 在in子查询中，就是value in (select...)把形如“select unique_key_column”的子查询替换。<br>PS：所以不一定in子句中使用子查询就是低效的！
index_subquery	| 同上，但把形如”select non_unique_key_column“的子查询替换
range 	| 常数值的范围
index	| a.当查询是索引覆盖的，即所有数据均可从索引树获取的时候（Extra中有Using Index)<br>b.以索引顺序从索引中查找数据行的全表扫描（无 Using Index）；<br>c.如果Extra中Using Index与Using Where同时出现的话，则是利用索引查找键值的意思；<br>d.如单独出现，则是用读索引来代替读行，但不用于查找<br>
all	| 全表扫描

###### 第十二条
执行次数: 135 最大耗时: 3秒 解析最大行数:78395   返回最大行数 0

```
select distinct userid from weekhosnominate 
where userid = 351211 and datatype = 4
```


###### 分析

![](https://i.loli.net/2019/01/29/5c500bb3e5b0a.png)


###### 方案


```
ALTER TABLE `weekhosnominate` ADD INDEX UserID(`UserID`);
```



再次执行explain分析

![](https://i.loli.net/2019/01/29/5c500bc97338d.png)


###### 结果
匹配范围 rows 从1w缩小到288

##### 第十三条
执行次数: 110 最大耗时: 2秒 解析最大行数:87693   返回最大行数 1


```
select `inspectioninfo`.`itemmsg` from `inspectioninfo` 
where ( itemid in ( 30 ,31 ) and itemtype = 0
and inspectionid = 109 ) limit 1 ;
```


###### 分析

![](https://i.loli.net/2019/01/29/5c500bc97338d.png)


###### 方案:
增加索引


```
ALTER TABLE `inspectioninfo` ADD INDEX 
InspectionID(`InspectionID`);
```


再次执行explain分析

![](https://i.loli.net/2019/01/29/5c500c31f3691.png)


###### 结果
匹配范围 rows  从 5w 缩小到 13


##### 第十四条语句
执行次数: 103 最大耗时: 2秒 解析最大行数:78395   返回最大行数 0


```
select `weekhosnominate`.`id` from `weekhosnominate` 
where ( userid = 351211 );
```



###### 分析:

![](https://i.loli.net/2019/01/29/5c500c6fe4fb4.png)


###### 方案:
通过给字段 userid 建立索引来区分,缩小范围


```
ALTER TABLE `weekhosnominate` ADD INDEX UserID(UserID) ;
```



再次执行explain分析可以发现,
通过索引 userid 将范围由全表扫描的近万到索引指向的数十条记录.

![](https://i.loli.net/2019/01/29/5c500c90601da.png)


###### 结果:
匹配范围 rows 从 9k 缩小到 288



###### 深入理解:

![](https://i.loli.net/2019/01/29/5c500cc4e63ca.png)
mysql结构


##### mysql索引原理

索引目的<br>
索引的目的在于提高查询效率，可以类比字典，如果要查“mysql”这个单词，我们肯定需要定位到m字母，然后从下往下找到y字母，再找到剩下的sql。如果没有索引，那么你可能需要把所有单词看一遍才能找到你想要的，如果我想找到m开头的单词呢？或者ze开头的单词呢？是不是觉得如果没有索引，这个事情根本无法完成？

索引原理<br>
除了词典，生活中随处可见索引的例子，如火车站的车次表、图书的目录等。它们的原理都是一样的，通过不断的缩小想要获得数据的范围来筛选出最终想要的结果，同时把随机的事件变成顺序的事件，也就是我们总是通过同一种查找方式来锁定数据。

数据库也是一样，但显然要复杂许多，因为不仅面临着等值查询，还有范围查询(>、<、between、in)、模糊查询(like)、并集查询(or)等等。数据库应该选择怎么样的方式来应对所有的问题呢？我们回想字典的例子，能不能把数据分成段，然后分段查询呢？最简单的如果1000条数据，1到100分成第一段，101到200分成第二段，201到300分成第三段……这样查第250条数据，只要找第三段就可以了，一下子去除了90%的无效数据。但如果是1千万的记录呢，分成几段比较好？稍有算法基础的同学会想到搜索树，其平均复杂度是lgN，具有不错的查询性能。但这里我们忽略了一个关键的问题，复杂度模型是基于每次相同的操作成本来考虑的，数据库实现比较复杂，数据保存在磁盘上，而为了提高性能，每次又可以把部分数据读入内存来计算，因为我们知道访问磁盘的成本大概是访问内存的十万倍左右，所以简单的搜索树难以满足复杂的应用场景。

磁盘IO与预读<br>
前面提到了访问磁盘，那么这里先简单介绍一下磁盘IO和预读，磁盘读取数据靠的是机械运动，每次读取数据花费的时间可以分为寻道时间、旋转延迟、传输时间三个部分，寻道时间指的是磁臂移动到指定磁道所需要的时间，主流磁盘一般在5ms以下；旋转延迟就是我们经常听说的磁盘转速，比如一个磁盘7200转，表示每分钟能转7200次，也就是说1秒钟能转120次，旋转延迟就是1/120/2 = 4.17ms；传输时间指的是从磁盘读出或将数据写入磁盘的时间，一般在零点几毫秒，相对于前两个时间可以忽略不计。那么访问一次磁盘的时间，即一次磁盘IO的时间约等于5+4.17 = 9ms左右，听起来还挺不错的，但要知道一台500 -MIPS的机器每秒可以执行5亿条指令，因为指令依靠的是电的性质，换句话说执行一次IO的时间可以执行40万条指令，数据库动辄十万百万乃至千万级数据，每次9毫秒的时间，显然是个灾难。下图是计算机硬件延迟的对比图，供大家参考：<br>


![](https://i.loli.net/2019/01/29/5c500d3c3da00.png)硬件处理延迟





###### REFER:
[MySQL索引原理及慢查询优化](https://tech.meituan.com/2014/06/30/mysql-index.html)
