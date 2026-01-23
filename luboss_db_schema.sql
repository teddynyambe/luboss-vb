-- MySQL dump 10.13  Distrib 8.0.44, for Linux (x86_64)
--
-- Host: localhost    Database: village_bank
-- ------------------------------------------------------
-- Server version	8.0.44-0ubuntu0.24.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `loan`
--

DROP TABLE IF EXISTS `loan`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `loan` (
  `id` char(36) NOT NULL,
  `member_id` char(36) NOT NULL,
  `application_date` timestamp NULL DEFAULT NULL,
  `effective_month` date DEFAULT NULL,
  `loan_amount` decimal(10,2) DEFAULT NULL,
  `percentage_interest` decimal(5,2) DEFAULT NULL,
  `repayment_start_date` date DEFAULT NULL,
  `repayment_end_date` date DEFAULT NULL,
  `number_of_instalments` int DEFAULT NULL,
  `loan_status` enum('pending','disbursed','approved','closed','open','withdrawn','rejected') DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `member_id` (`member_id`),
  CONSTRAINT `loan_ibfk_1` FOREIGN KEY (`member_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `loan_related_transaction`
--

DROP TABLE IF EXISTS `loan_related_transaction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `loan_related_transaction` (
  `id` char(36) NOT NULL,
  `transaction_id` char(36) NOT NULL,
  `loan_id` char(36) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `transaction_id` (`transaction_id`),
  KEY `loan_id` (`loan_id`),
  CONSTRAINT `loan_related_transaction_ibfk_1` FOREIGN KEY (`transaction_id`) REFERENCES `transaction` (`id`),
  CONSTRAINT `loan_related_transaction_ibfk_2` FOREIGN KEY (`loan_id`) REFERENCES `loan` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `penalty_record`
--

DROP TABLE IF EXISTS `penalty_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `penalty_record` (
  `id` char(36) NOT NULL,
  `member_id` char(36) NOT NULL,
  `penalty_type_id` char(36) NOT NULL,
  `date_issued` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `approved` tinyint(1) DEFAULT NULL,
  `added_by_id` char(36) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `member_id` (`member_id`),
  KEY `penalty_type_id` (`penalty_type_id`),
  KEY `added_by_id` (`added_by_id`),
  CONSTRAINT `penalty_record_ibfk_1` FOREIGN KEY (`member_id`) REFERENCES `user` (`id`),
  CONSTRAINT `penalty_record_ibfk_2` FOREIGN KEY (`penalty_type_id`) REFERENCES `penalty_type` (`id`),
  CONSTRAINT `penalty_record_ibfk_3` FOREIGN KEY (`added_by_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `penalty_type`
--

DROP TABLE IF EXISTS `penalty_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `penalty_type` (
  `id` char(36) NOT NULL,
  `description` varchar(255) NOT NULL,
  `fee` decimal(10,2) NOT NULL,
  `date_added` timestamp NULL DEFAULT (now()),
  `name` varchar(100) NOT NULL DEFAULT '',
  `enabled` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `savings_declaration`
--

DROP TABLE IF EXISTS `savings_declaration`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `savings_declaration` (
  `id` char(36) NOT NULL,
  `member_id` char(36) NOT NULL,
  `effective_month` date DEFAULT NULL,
  `declared_savings_amount` decimal(10,2) DEFAULT NULL,
  `declared_social_fund` decimal(10,2) DEFAULT NULL,
  `declared_admin_fund` decimal(10,2) DEFAULT NULL,
  `declared_penalties` decimal(10,2) DEFAULT NULL,
  `declared_interest_on_loan` decimal(10,2) DEFAULT NULL,
  `declared_loan_repayment` decimal(10,2) DEFAULT NULL,
  `actual_savings_amount` decimal(10,2) DEFAULT NULL,
  `actual_social_fund` decimal(10,2) DEFAULT NULL,
  `actual_admin_fund` decimal(10,2) DEFAULT NULL,
  `actual_penalties` decimal(10,2) DEFAULT NULL,
  `actual_interest_on_loan` decimal(10,2) DEFAULT NULL,
  `actual_loan_repayment` decimal(10,2) DEFAULT NULL,
  `actual_total_amount` decimal(10,2) DEFAULT NULL,
  `proof_document` varchar(255) DEFAULT NULL,
  `status` enum('pending','proof','approved','rejected') DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `member_id` (`member_id`),
  CONSTRAINT `savings_declaration_ibfk_1` FOREIGN KEY (`member_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `transaction`
--

DROP TABLE IF EXISTS `transaction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction` (
  `id` char(36) NOT NULL,
  `member_id` char(36) NOT NULL,
  `transaction_type` enum('savings','loan_repayment','penalty','interest','loan_disbured','withdrawal','social_fund','admin_fee') DEFAULT NULL,
  `amount` decimal(10,2) DEFAULT NULL,
  `related_savings_id` char(36) DEFAULT NULL,
  `date` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `member_id` (`member_id`),
  KEY `related_savings_id` (`related_savings_id`),
  CONSTRAINT `transaction_ibfk_1` FOREIGN KEY (`member_id`) REFERENCES `user` (`id`),
  CONSTRAINT `transaction_ibfk_2` FOREIGN KEY (`related_savings_id`) REFERENCES `savings_declaration` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` char(36) NOT NULL,
  `first_name` varchar(100) DEFAULT NULL,
  `last_name` varchar(100) DEFAULT NULL,
  `email` varchar(255) NOT NULL,
  `phone_number` varchar(20) DEFAULT NULL,
  `bank_account` varchar(50) DEFAULT NULL,
  `bank_name` varchar(100) DEFAULT NULL,
  `bank_branch` varchar(100) DEFAULT NULL,
  `nrc_number` varchar(50) DEFAULT NULL,
  `physical_address` text,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('admin','treasurer','member','compliance') DEFAULT 'member',
  `approved` tinyint(1) DEFAULT NULL,
  `first_name_next_of_kin` varchar(100) DEFAULT NULL,
  `last_name_next_of_kin` varchar(100) DEFAULT NULL,
  `phone_number_next_of_kin` varchar(20) DEFAULT NULL,
  `date_joined` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `nrc_number` (`nrc_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping routines for database 'village_bank'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-22 22:06:54
