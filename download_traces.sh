#!/bin/bash
# Downloads all evaluation traces from the CMU PDL Trace Repository.
# These are the traces used in Figures 8 and 12 of the paper.

set -e

TRACES_DIR="libcachesim/data"
mkdir -p "$TRACES_DIR"
cd "$TRACES_DIR"

BASE="https://ftp.pdl.cmu.edu/pub/datasets"

# MSR (Block)
wget -O wMSR.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/msr/msr_src1_1.oracleGeneral.zst"

# Meta (CDN)
wget -O wMetaCDN.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/metaCDN/meta_reag.oracleGeneral.zst"

# Meta (KV)
wget -O wMetaKVCache.oracleGeneral.bin.zst "$BASE/cacheDatasets/cacheDatasets/metaKV/meta_kvcache_traces_1.oracleGeneral.bin.zst"

# Meta (Block)
wget -O wMetaStorage.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/metaStorage/block_traces_5.oracleGeneral.bin.zst"

# Tencent (Object)
wget -O wTencent.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/tencentBlock/v2/tencentBlock_1069.oracleGeneral.zst"

# Twitter (KV)
wget -O wTwemCacheCluster50.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/twitter/sample10/cluster50.oracleGeneral.sample10.zst"
wget -O wTwemCacheCluster53.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/twitter/sample10/cluster53.oracleGeneral.sample10.zst"

# WikiMedia (CDN)
wget -O wWikiMedia.oracleGeneral.bin.zst "$BASE/twemcacheWorkload/cacheDatasets/wiki/wiki_2019t.oracleGeneral.zst"

echo "All traces downloaded to $TRACES_DIR/"
