import sys
import subprocess
from files import *
from fasta import *
import vcf
from collections import defaultdict
import itertools
import json
from tqdm import tqdm

v = True
class bcf:
	def __init__(self,filename,prefix=None,threads=4):
		self.params = {}
		self.samples = []
		self.params["bcf"] = filename
		self.params["threads"] = threads
		if prefix==None:
			self.params["prefix"] = filename[:-4] if filename[-4:]==".bcf" else filename
		else:
			self.params["prefix"] = prefix
		self.params["temp_file"] = "%s.temp" % self.params["prefix"]
		self.params["vcf"] = "%(prefix)s.vcf" % self.params
		index_bcf(filename,self.params["threads"])
		cmd = "bcftools query -l %(bcf)s > %(temp_file)s" % self.params
		run_cmd(cmd,verbose=v)
		for l in open(self.params["temp_file"]):
			self.samples.append(l.rstrip())
		os.remove(self.params["temp_file"])

	def annotate(self,ref_file,gff_file):
		self.params["ref_file"] = ref_file
		self.params["gff_file"] = gff_file
		self.params["ann_file"] = "%s.ann.bcf" % self.params["prefix"]
		cmd = "bcftools csq -f %(ref_file)s -g %(gff_file)s %(bcf)s -o %(ann_file)s" % self.params
		run_cmd(cmd,verbose=v)

	def extract_matrix(self,matrix_file=None):
		self.params["matrix_file"] = matrix_file if matrix_file==True else self.params["prefix"]+".mat"
		O = open(self.params["matrix_file"],"w").write("chr\tpos\tref\t%s\n" % ("\t".join(self.samples)))
		cmd = "bcftools view %(bcf)s | bcftools query -f '%%CHROM\\t%%POS\\t%%REF[\\t%%IUPACGT]\\n'  | sed 's/\.\/\./N/g' >> %(matrix_file)s" % self.params
		run_cmd(cmd,verbose=v)

	def vcf_to_fasta(self,filename,threads=20):
		"""Create a fasta file from the SNPs"""
		self.params["threads"] = threads
		cmd = "bcftools query -l %(bcf)s | parallel -j %(threads)s \"(printf '>'{}'\\n' > {}.fa; bcftools view -v snps %(bcf)s | bcftools query -s {} -f '[%%IUPACGT]'  >> {}.fa; printf '\\n' >> {}.fa)\"" % self.params
		run_cmd(cmd)
		O = open(filename,"w")
		for s in self.samples:
			fdict = fasta(s+".fa").fa_dict
			fdict[s] = fdict[s].replace("./.","N")
			O.write(">%s\n%s\n" % ( s,fdict[s]))
			os.remove(s+".fa")
		O.close()

	def bcf2vcf(self):
		if nofile(self.params["vcf"]):
			cmd = "bcftools view %(bcf)s -Ov -o %(vcf)s" % self.params
			run_cmd(cmd)

	def get_variants(self):
		if nofile(self.params["vcf"]): self.bcf2vcf()
		vcf_reader = vcf.Reader(open(self.params["vcf"],"r"))
		results = defaultdict(lambda:defaultdict(dict))
		for record in vcf_reader:
			for s in record.samples:
				results[record.CHROM][record.POS][s.sample] = s.gt_bases.split("/")[0]
		return results

	def get_venn_diagram_data(self,samples,outfile):
		samples = samples.split(",")
		if len(samples)>4:
			print samples
			print "Can't handle more than 4 samples...Exiting!"
			quit()
		if nofile(self.params["vcf"]): self.bcf2vcf()
		vcf_reader = vcf.Reader(open(self.params["vcf"],"r"))
		results = defaultdict(int)
		tot_snps = defaultdict(int)
		data = defaultdict(int)

		for record in vcf_reader:
			tmp = []
			for s in record.samples:
				if s.sample not in samples: continue
				if s.gt_nums=="1/1":
					tmp.append(s.sample)
					tot_snps[s.sample]+=1
			for x in itertools.combinations(tmp,2):
				tmp_str = "_".join(sorted([str(samples.index(d)) for d in x]))
				data["overlap_"+tmp_str] +=1
			for x in itertools.combinations(tmp,3):
				tmp_str = "_".join(sorted([str(samples.index(d)) for d in x]))
				data["overlap_"+tmp_str] +=1
			for x in itertools.combinations(tmp,4):
				tmp_str = "_".join(sorted([str(samples.index(d)) for d in x]))
				data["overlap_"+tmp_str] += 1
		for i,si in enumerate(samples):
			if si not in self.samples:
				print "Can't find %s in samples...Exiting" % si
				quit()
			data["id_%s"%i] = si
			data["tot_snps_%s"%i] = tot_snps[si]
		data["outfile"] = outfile
		if len(samples)==2:
			rscript = """
library(VennDiagram)
pdf("%(outfile)s")
draw.pairwise.venn(area1=%(tot_snps_0)s, area2=%(tot_snps_1)s, cross.area=%(overlap_0_1)s, category = c("%(id_0)s","%(id_1)s"),fill=rainbow(2))
dev.off()
""" % data
		elif len(samples)==3:
			rscript = """
library(VennDiagram)
pdf("%(outfile)s")
draw.triple.venn(area1=%(tot_snps_0)s, area2=%(tot_snps_1)s, area3=%(tot_snps_2)s, n12=%(overlap_0_1)s, n23=%(overlap_1_2)s, n13=%(overlap_0_2)s, n123=%(overlap_0_1_2)s, category = c("%(id_0)s","%(id_1)s","%(id_2)s"),fill=rainbow(3))
dev.off()
""" % data
		elif len(samples)==4:
			rscript="""
library(VennDiagram)
pdf("%(outfile)s")
draw.quad.venn(area1=%(tot_snps_0)s, area2=%(tot_snps_1)s, area3=%(tot_snps_2)s, area4=%(tot_snps_3)s,
n12=%(overlap_0_1)s, n13=%(overlap_0_2)s, n14=%(overlap_0_3)s, n23=%(overlap_1_2)s, n24=%(overlap_1_3)s, n34=%(overlap_2_3)s,
n123=%(overlap_0_1_2)s, n124=%(overlap_0_1_3)s, n134=%(overlap_0_2_3)s, n234=%(overlap_1_2_3)s,
n1234=%(overlap_0_1_2_3)s,
category = c("%(id_0)s","%(id_1)s","%(id_2)s","%(id_3)s"),fill=rainbow(4))
dev.off()
""" % data
		temp_r_script = "%s.temp.R" % self.params["prefix"]
		open(temp_r_script,"w").write(rscript)
		cmd = "Rscript %s" % temp_r_script
		run_cmd(cmd)
		rm_files([temp_r_script])
	def merge_in_snps(self,bcf,outfile):
		self.params["new_bcf"] = bcf
		self.params["targets_file"] = "%(prefix)s.targets" % self.params
		self.params["tmp_file"] = "%(prefix)s.temp.bcf" % self.params
		self.params["tmp2_file"] = "%(prefix)s.temp2.bcf" % self.params
		self.params["outfile"] = outfile
		cmd = "bcftools view -v snps %(bcf)s | bcftools query -f '%%CHROM\\t%%POS\\n' | awk '{print $1\"\t\"$2-1\"\t\"$2}' > %(targets_file)s" % self.params
		run_cmd(cmd)
		cmd = "bcftools view -T %(targets_file)s %(new_bcf)s -Ob -o %(tmp_file)s" % self.params
		run_cmd(cmd)
		index_bcf(self.params["tmp_file"],self.params["threads"])
		cmd = "bcftools view -T %(targets_file)s %(bcf)s -Ob -o %(tmp2_file)s" % self.params
		run_cmd(cmd)
		index_bcf(self.params["tmp2_file"],self.params["threads"])
		cmd = "bcftools merge --threads %(threads)s %(tmp2_file)s %(tmp_file)s | bcftools view -i 'F_MISSING<0.5' -Ob -o %(outfile)s" % self.params
		run_cmd(cmd)

	def annotate_from_bed(self,bed_file):
		temp_bed = "%s.temp.bed" % self.params["prefix"]
		temp_vcf = "%s.temp.vcf" % self.params["prefix"]
		cmd = "awk '{print $1\"\t\"$2-1\"\t\"$2}' %s > %s" % (bed_file,temp_bed)
		run_cmd(cmd)
		cmd = "bcftools view -T %s %s -o %s " % (temp_bed,self.params["bcf"],temp_vcf)
		run_cmd(cmd)
		bed_dict = defaultdict(dict)
		for l in open(bed_file):
			#chrom pos pos allele data
			row = l.rstrip().split()
			bed_dict[row[0]][int(row[1])] = (row[3],row[4])
		vcf_reader = vcf.Reader(open(temp_vcf))
		results = defaultdict(list)
		for record in vcf_reader:
			for s in record.samples:
				if s.gt_bases==None: continue
				nuc = s.gt_bases.split("/")[0]
				if nuc==bed_dict[record.CHROM][record.POS][0]:
					results[s.sample].append(bed_dict[record.CHROM][record.POS][1])
		for s in self.samples:
			print "%s\t%s" % (s,";".join(sorted(list(set(results[s])))))
	def extract_compressed_json(self,outfile):
		self.bcf2vcf()
		vcf_reader = vcf.Reader(open(self.params["vcf"]))
		results = defaultdict(lambda: defaultdict(dict))
		for record in tqdm(vcf_reader):
			tmp = defaultdict(list)
			for s in record.samples:
				if s.gt_bases==None:
					tmp["N"].append(self.samples.index(s.sample))
				elif s.gt_nums=="1/1":
					tmp[s.gt_bases.split("/")[0]].append(self.samples.index(s.sample))

			results[record.CHROM][record.POS] = tmp
		json.dump({"variants":results,"samples":self.samples},open(outfile,"w"))
