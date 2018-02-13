#!/usr/bin/env python3


# IMPORTS
import os
import re
import sys
import json
import gzip
import yaml
import time
import enchant  # english dict
import requests
import networkx as nx
import mysql.connector  # sudo pip3 install mysql-connector-python
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
from nltk.corpus import stopwords
from clint.textui import progress
from nltk.tokenize import RegexpTokenizer
from nltk.stem.wordnet import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer


# INFORMATIONS
__author__ = 'Emeric DYNOMANT'
__copyright__ = 'CC'
__version__ = '1.0'
__maintainer__ = 'Emeric DYNOMANT'
__email__ = 'emeric.dynomant@gmail.com'
__status__ = 'Alpha'


# DOCUMENTATION
# Wiki dumps DL page: 					https://dumps.wikimedia.org/enwiki/20171220/
# SO feed to get some informations :	https://stackoverflow.com/questions/17432254/wikipedia-category-hierarchy-from-dumps
# Relation explanations:				https://kodingnotes.wordpress.com/2014/12/03/parsing-wikipedia-page-hierarchy/
# Wikipedia manuals:					https://www.mediawiki.org/wiki/Manual:Categorylinks_table
# Ontology creation: 					https://www.ccri.com/2018/01/22/deep-learning-ontology-development/


class Builder(object):
	"""Let's download every requiered data on Wikipedia and build an ontology from it."""

	def __init__(self):
		print()
		with open('./configurations/configuration.yaml', 'r') as config_file:
			self.configuration = yaml.load(config_file)
		# NLP
		self.stopwords = set(stopwords.words('english') + ['false', 'true', 'ext', 'doi'])
		self.tokenizer = RegexpTokenizer(r'\w+')
		self.lemmatizer = WordNetLemmatizer()
		self.english_dict = enchant.Dict('en_US')
		# DOWNLOAD
		self.download_url = 'https://dumps.wikimedia.org/enwiki/latest/'
		self.requiered_filenames = ['enwiki-latest-categorylinks.sql.gz', 'enwiki-latest-category.sql.gz', 'enwiki-latest-page.sql.gz']
		# SQL CONNECTION
		with open('./configurations/mysql.yaml', 'r') as mysql_config_file:
			self.mysql_file = yaml.load(mysql_config_file)
		self.mysql_config = {
			'host': str(self.mysql_file['mysql']['host']),
			'user': str(self.mysql_file['mysql']['user']),
			'database': 'wikipedia',
			'password': str(self.mysql_file['mysql']['password']),
			'use_pure': True,
			'raise_on_warnings': True,
			'get_warnings': True,
			'autocommit': True
		}

	def download_data(self):
		"""Download on wiki website the 3 requiered dumps (~ 1.5Go + 21Mo + 2.2Go)"""
		if self.configuration['program_steps']['download_data'] is True:
			for sql_file in self.requiered_filenames:
				print('Downloading {}'.format(sql_file))
				data = requests.get('{}{}'.format(self.download_url, sql_file), stream=True)
				if data.status_code == 200:
					with open('./wiki_dumps/raw/{}'.format(sql_file), 'wb') as data_file:
						total_length = int(data.headers.get('content-length'))
						# Just to see a progressbar, cause it's cool as hell
						for chunk in progress.bar(data.iter_content(chunk_size=1024), expected_size=(total_length/1024) + 1):
							if chunk:
								data_file.write(chunk)
								data_file.flush()
				else:
					print('Something went wrong with your download. Please try again')
					exit(0)

	def extract_data(self):
		"""Extract gz files got by get_data()"""
		if self.configuration['program_steps']['download_data'] is True:
			for gz_file in os.listdir('./wiki_dumps/raw/'):
				print('Extraction {}'.format(gz_file))
				with gzip.open('./wiki_dumps/raw/{}'.format(gz_file), 'rb') as archive:
					content = archive.read()
					with open('./wiki_dumps/extracted/{}'.format(re.sub('\.gz', '', gz_file)), 'wb') as sql_file:
						sql_file.write(content)

	def insert_data(self):
		"""Create a DB named 'wikipedia' and insert those 3 tables into it. Watch out, it'll take some time."""
		if self.configuration['program_steps']['insert_data'] is True:
			try:
				connection = mysql.connector.connect(**self.mysql_config, buffered=True)
				cursor = connection.cursor()
				cursor.execute('CREATE DATABASE wikipedia ;')
				connection.close()
			except mysql.connector.errors.DatabaseError:
				print('Database [wikipedia] already exists.')
				pass
			# Now, insertion
			for sql_dump in os.listdir('./wiki_dumps/extracted/'):
				print('Inserting {}'.format(sql_dump))
				os.system('mysql -u {} -h {} -D wikipedia -p{} < ./wiki_dumps/extracted/{}'.format(self.mysql_config['user'], self.mysql_config['host'], self.mysql_config['password'], sql_dump))

	def get_id(self, category_name, connection):
		"""Get the ID of a CATEGORY page from its name"""
		cursor = connection.cursor()
		command = 'SELECT page_id FROM page WHERE CONVERT(page_title, CHAR(255)) = %(page_title)s AND page_namespace = 14;'
		data = {'page_title': category_name}
		cursor.execute(command, data)
		ids_linked = [id_[0] for id_ in cursor]
		cursor.close()
		try:
			category_id = ids_linked[0]
		except (IndexError, ValueError):
			print('\nYour initial request is not a Wikipedia category. Please use a more general term or try plural form.\n')
			exit(0)
		return category_id

	def get_name(self, id_category, connection):
		"""Get page name from its ID"""
		cursor = connection.cursor()
		command = 'SELECT CONVERT(page_title, CHAR(100)) FROM page WHERE page_id = %(page_id)s ;'
		data = {'page_id': id_category}
		cursor.execute(command, data)
		names = [name[0] for name in cursor]
		cursor.close()
		return names[0]

	def get_linked_names(self, id_category, connection):
		"""Get names of every pages linked to an ID category"""
		cursor = connection.cursor()
		command = 'SELECT CONVERT(cl_to, CHAR(100)) FROM categorylinks INNER JOIN page ON categorylinks.cl_from = page.page_id WHERE cl_from = %(id_category)s ;'
		data = {'id_category': id_category}
		cursor.execute(command, data)
		linked_names = []
		for name in cursor:
			# Remove categories used by Wikipedia's admin
			if re.search('[Ww]ikipedia|[Cc]ateg|[Aa]cad|[Aa]rticle|[Tt]opic', name[0]) is None:
				linked_names.append(name[0])
		return linked_names

	def draw_graph(self, graph, title, node_alpha=0.3, edge_alpha=0.3, edge_tickness=1, edge_text_pos=0.3, text_font='sans-serif'):
		"""Draw a noded graph."""
		G = nx.Graph()
		# Add edges
		for edge in graph:
			G.add_edge(edge[0], edge[1])
		# Base layout is SHELL, but SPRING is nicer for networks (possibles: SPECTRAL, SPRING, RANDOM, SHELL)
		graph_pos = nx.spring_layout(G)
		# Draw graph
		plt.figure(figsize=(self.configuration['graph']['width'], self.configuration['graph']['height']), dpi=self.configuration['graph']['dpi'])
		nx.draw_networkx_nodes(G, graph_pos, node_size=self.configuration['graph']['node_size'], alpha=node_alpha, node_color=self.configuration['graph']['node_color'])
		nx.draw_networkx_edges(G, graph_pos, width=edge_tickness, alpha=edge_alpha, edge_color=self.configuration['graph']['edge_color'])
		nx.draw_networkx_labels(G, graph_pos, font_size=self.configuration['graph']['node_text_size'], font_family=text_font)
		# Add numbers for edge name if empty
		labels = range(len(graph))
		edge_labels = dict(zip(graph, labels))
		nx.draw_networkx_edge_labels(G, graph_pos, edge_labels=edge_labels, label_pos=edge_text_pos)
		plt.savefig('./terminologies/wikipedia_ontology_{}.png'.format(title))

	def build_step(self, relations, parent_name, connection, categories_linked):
		"""Build a link between two categories"""
		parent_id = self.get_id(category_name=parent_name, connection=connection)
		children_names = self.get_linked_names(id_category=parent_id, connection=connection)
		categories_linked
		for child_name in children_names:
			# Keep track of unique categories linked
			if child_name not in categories_linked:
				categories_linked.append(child_name)
			if (parent_name, child_name) not in relations:
				relations = relations + [(parent_name, child_name)]
		sys.stdout.write('\t{} links created with {} unique categories.\r'.format(len(relations), len(categories_linked)))
		sys.stdout.flush()
		return relations, children_names, categories_linked

	def build_relations(self, top_term, number_of_categories):
		"""Loop overt time to build the ontology thanks to every links created between nodes in the graph"""
		connection = mysql.connector.connect(**self.mysql_config, buffered=True)
		# Get data from the top node
		parent_name = top_term
		relations = []
		categories_linked = []
		loop = True
		while loop is True:
			relations, children_names, categories_linked = self.build_step(relations=relations, parent_name=parent_name, categories_linked=categories_linked, connection=connection)
			for parent_name in children_names:
				relations, children_names, categories_linked = self.build_step(relations=relations, parent_name=parent_name, categories_linked=categories_linked, connection=connection)
				# Stop after a given number of links. The printed number is always greater due to looping into children names.
				if len(categories_linked) > number_of_categories:
					loop = False
		# Plot graphe
		print('\t{} links created with {} unique categories.\r'.format(len(relations), len(categories_linked)))
		if self.configuration['program_steps']['plot_graph'] is True:
			self.draw_graph(graph=relations, title=top_term)
		return relations

	def get_linked_pages(self, relations):
		"""Select linked pages to a catégory"""
		connection = mysql.connector.connect(**self.mysql_config, buffered=True)
		cursor = connection.cursor()
		linked_pages = {}
		parent_uniques = []
		number_childrens = 0
		# For every category in the graph, get unique parent
		for relation in relations:
			if relation[0] not in parent_uniques:
				parent_uniques.append(relation[0])
			elif relation[1] not in parent_uniques:
				parent_uniques.append(relation[1])
		# And for each
		for parent in parent_uniques:
			pages = []
			command = 'SELECT cl_from FROM categorylinks WHERE cl_to = BINARY(%(parent)s) ;'
			data = {'parent': parent}
			cursor.execute(command, data)
			linked_pages_ids = [id_[0] for id_ in cursor]
			# Get pages name
			for page_id in linked_pages_ids:
				command = 'SELECT CONVERT(page_title, CHAR(255)) FROM page WHERE page_id = %(page_id)s ;'
				data = {'page_id': page_id}
				cursor.execute(command, data)
				page_title = [title[0] for title in cursor]
				if re.search('[Ww]ikipedia|[Cc]ateg|[Aa]cad', page_title[0]) is None:
					pages.append(page_title[0])
					number_childrens += 1
			linked_pages[parent] = pages
		print('\tTotal of {} pages linked.'.format(number_childrens))

		return linked_pages

	def clean_xml(self, text):
		"""Clean the raw data from webpage scrapping"""
		text = re.sub('<.*?>', '', str(text))
		text = re.sub('[0-9]', '', str(text))
		text = re.sub('\t', '', str(text))
		text = re.sub('\n', ' ', str(text))
		return text

	def get_vocabulary(self, linked_pages, categories_links):
		"""Scrapp a wiki page to get vocabulary for each category"""
		total_vocabulary = {}
		unique_vocabulary = []
		unique_vocabulary_tfidf = []
		# For each category
		for parent, pages in linked_pages.items():
			children_pages = []
			downloaded_pages = []
			# For every pages linked to this wategory on Wiki
			for page in pages:
				sys.stdout.write('\t{} / {} pages downloaded for [{}] category.\r'.format(len(children_pages)-1, len(pages), parent))
				sys.stdout.flush()
				# Get data
				wiki_url = 'https://en.wikipedia.org/wiki/{}'.format(page)
				data = requests.get(wiki_url)
				data_soup = BeautifulSoup(data.text, 'html.parser')
				paragraphs = [str(paragraph) for paragraph in data_soup.find_all('p')]
				paragraphs_joined = ' '.join(paragraphs)
				# Clean, tokenize, stemm and rebuild the document
				page_vocabulary = []
				cleaned_data = self.clean_xml(text=paragraphs_joined.strip())
				tokenized_data = self.tokenizer.tokenize(cleaned_data)
				for token in tokenized_data:
					if token.lower() not in self.stopwords:
						word = self.lemmatizer.lemmatize(token.lower())
						# Check if the word is correct
						if self.english_dict.check(word) is True:
							page_vocabulary.append(word)
							# Track total vocabulary
							if word not in unique_vocabulary:
								unique_vocabulary.append(word)
							# Here, why not Levenstein for correction, but gonna be long
				page_nlp_treated = ' '.join(page_vocabulary)
				if len(children_pages) >= self.configuration['options']['pages_per_category'] or len(children_pages) == len(pages):
					break
				else:
					children_pages.append(page_nlp_treated)
					downloaded_pages.append(page)
				# Wikipedia is cool, be cool with their servers.
				time.sleep(self.configuration['options']['waiting_time'])
			# StdOut summary
			print('\n\t\t- ' + '\n\t\t- '.join(downloaded_pages))
			# TF_IDF for vocabulary of each category and get top score
			tf = TfidfVectorizer(analyzer='word', ngram_range=(1,5), min_df=0, stop_words=self.stopwords)
			tfidf_matrix = tf.fit_transform(children_pages)
			feature_names = tf.get_feature_names()
			dense = tfidf_matrix.todense()
			episode = dense[0].tolist()[0]
			phrase_scores = [pair for pair in zip(range(0, len(episode)), episode) if pair[1] > 0]
			sorted_phrase_scores = sorted(phrase_scores, key=lambda t: t[1] * -1)
			category_words = []
			for word, score in [(feature_names[word_id], score) for (word_id, score) in sorted_phrase_scores][:self.configuration['options']['word_per_page']]:
				category_words.append({word: score})
				if word not in unique_vocabulary_tfidf:
					unique_vocabulary_tfidf.append(word)
			# Get linked categories to category
			linked_categories = []
			for relation in relations:
				if relation[0] == parent and relation[0] not in linked_categories:
					linked_categories.append(relation[1])
				if relation[1] == parent and relation[1] not in linked_categories:
					linked_categories.append(relation[0])
			# Get linked pages to category
			for category, pages in linked_pages.items():
				if category == parent:
					linked_pages_to_category = pages
			category_details = {}
			category_details['terminology'] = category_words
			category_details['linked_pages_to_category'] = linked_pages_to_category
			category_details['linked_categories'] = linked_categories
			total_vocabulary[parent] = category_details
		# Statistics about our terminology
		print('\nA total of {} words have been scanned to extract {} important words covering {} categories.'.format(len(unique_vocabulary), len(unique_vocabulary_tfidf), len(linked_pages)))
		return total_vocabulary

	def write_terminology(self, terminology, top_term):
		"""Write a simple JSON file containing our terminology"""
		with open('./terminologies/{}_terminology.json'.format(top_term), 'w') as json_file:
			json_file.write(json.dumps(terminology, sort_keys=True, indent=2, ensure_ascii=False))
		print('Terminology has been written to file [./{}_terminology.json]'.format(top_term))
		print()


if __name__ == '__main__':

	ChuckNorris = Builder()
	top_term = re.sub(' ', '_', input('Please enter a term: '))
	ChuckNorris.download_data()
	ChuckNorris.extract_data()
	ChuckNorris.insert_data()
	relations = ChuckNorris.build_relations(top_term=top_term, number_of_categories=5)
	linked_pages = ChuckNorris.get_linked_pages(relations=relations)
	terminology = ChuckNorris.get_vocabulary(linked_pages=linked_pages, categories_links=relations)
	ChuckNorris.write_terminology(terminology=terminology, top_term=top_term)
